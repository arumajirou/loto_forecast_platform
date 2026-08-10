from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .certification_io import (
    write_json,
    write_manifest_and_sums,
)
from .certification_models import (
    build_panel,
    compare_predictions,
    resolve_parameters,
)
from .contracts import ExpectedStatus
from .inventory import MODEL_NAMES, model_contract


def normalize_property(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, int, bool)):
        return value

    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value

    if isinstance(value, np.generic):
        return normalize_property(value.item())

    if isinstance(value, np.ndarray):
        return normalize_property(value.tolist())

    if isinstance(value, (tuple, list)):
        return [normalize_property(item) for item in value]

    if isinstance(value, dict):
        return {str(key): normalize_property(item) for key, item in value.items()}

    if hasattr(value, "get_params"):
        try:
            return {
                "class": (f"{type(value).__module__}.{type(value).__qualname__}"),
                "params": normalize_property(value.get_params(deep=False)),
            }
        except Exception:
            pass

    return repr(value)


def _direct_snapshot(
    model: Any,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    evidence: dict[str, Any] = {}

    for name, requested in parameters.items():
        requested_value = normalize_property(requested)

        if not hasattr(model, name):
            evidence[name] = {
                "mode": "MISSING_DIRECT_PROPERTY",
                "requested": requested_value,
                "effective": None,
                "match": False,
            }
            continue

        effective_value = normalize_property(getattr(model, name))

        evidence[name] = {
            "mode": "DIRECT",
            "requested": requested_value,
            "effective": effective_value,
            "match": requested_value == effective_value,
        }

    return evidence


def _autoregressive_snapshot(
    model: Any,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    lags = parameters["lags"]

    if isinstance(lags, int):
        expected_order = [lags, 0, 0]
        expected_fixed = None
    else:
        lag_values = list(lags)
        maximum = max(lag_values)

        expected_order = [maximum, 0, 0]
        expected_fixed = {
            f"ar{index}": ("NaN" if index in lag_values else 0)
            for index in range(
                1,
                maximum + 1,
            )
        }

    effective = {
        "order": normalize_property(model.order),
        "fixed": normalize_property(model.fixed),
    }

    expected = {
        "order": expected_order,
        "fixed": expected_fixed,
    }

    return {
        "lags": {
            "mode": "DERIVED",
            "requested": normalize_property(lags),
            "effective": effective,
            "expected": expected,
            "match": effective == expected,
        }
    }


def property_snapshot(
    model_name: str,
    model: Any,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    if model_name == "AutoRegressive":
        return _autoregressive_snapshot(
            model,
            parameters,
        )

    return _direct_snapshot(
        model,
        parameters,
    )


def property_snapshot_passes(
    snapshot: dict[str, Any],
) -> bool:
    return all(bool(evidence["match"]) for evidence in snapshot.values())


def _future_exog(
    model_name: str,
    panel: pd.DataFrame,
    horizon: int,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    if model_name != "SklearnModel":
        return panel, None

    panel = panel.copy(deep=True)

    panel["x1"] = np.sin(panel["ds"].to_numpy(dtype=float) / 5.0)

    future_rows: list[dict[str, Any]] = []

    for unique_id, group in panel.groupby(
        "unique_id",
        sort=False,
    ):
        last_ds = int(group["ds"].max())

        for step in range(1, horizon + 1):
            ds = last_ds + step

            future_rows.append(
                {
                    "unique_id": unique_id,
                    "ds": ds,
                    "x1": float(np.sin(ds / 5.0)),
                }
            )

    return panel, pd.DataFrame(future_rows)


def certify_property_lifecycle(
    *,
    run_dir: Path,
    model_name: str,
    core_class: type,
    models_module: Any,
    horizon: int = 1,
    seed: int = 1,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract = model_contract(model_name)

    result: dict[str, Any] = {
        "model_name": model_name,
        "property_status": "EXECUTION_FAILED",
    }

    model_dir = run_dir / "models" / model_name

    model_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        model_class = getattr(
            models_module,
            model_name,
        )

        parameters, unresolved = resolve_parameters(
            model_name,
            model_class,
            overrides,
        )

        result["requested_parameters"] = normalize_property(parameters)

        result["unresolved_parameters"] = list(unresolved)

        if unresolved:
            raise ValueError(f"unresolved parameters: {unresolved}")

        template = model_class(**parameters)

        constructed = property_snapshot(
            model_name,
            template,
            parameters,
        )

        result["constructed"] = constructed
        result["constructed_match"] = property_snapshot_passes(constructed)

        if contract.expected_status is ExpectedStatus.EXPECTED_NEGATIVE_PASS:
            result["fitted_status"] = "EXPECTED_NOT_APPLICABLE"
            result["loaded_status"] = "EXPECTED_NOT_APPLICABLE"
            result["property_status"] = "EXPECTED_NEGATIVE_CONTROL"

            write_json(
                model_dir / "property_result.json",
                result,
            )

            return result

        panel, profile = build_panel(
            model_name,
            seed=seed,
        )

        result["data_profile"] = profile

        panel, future_exog = _future_exog(
            model_name,
            panel,
            horizon,
        )

        engine = core_class(
            models=[template],
            freq=1,
            n_jobs=1,
        )

        engine.fit(df=panel.copy(deep=True))

        result["fitted_container_shape"] = list(engine.fitted_.shape)

        expected_shape = (
            panel["unique_id"].nunique(),
            1,
        )

        result["expected_fitted_shape"] = list(expected_shape)

        result["fitted_shape_match"] = engine.fitted_.shape == expected_shape

        fitted_models = [engine.fitted_[index, 0] for index in range(engine.fitted_.shape[0])]

        fitted = [
            property_snapshot(
                model_name,
                fitted_model,
                parameters,
            )
            for fitted_model in fitted_models
        ]

        result["fitted"] = fitted

        result["fitted_match"] = all(property_snapshot_passes(snapshot) for snapshot in fitted)

        # Diagnostic only: some valid models fit by updating existing
        # attributes rather than adding a new top-level attribute.
        result["fit_state_present"] = all(
            bool(set(vars(model)) - set(vars(template))) for model in fitted_models
        )

        result["fit_status"] = "VERIFIED" if result["fitted_shape_match"] else "FAILED"

        predict_kwargs: dict[str, Any] = {
            "h": horizon,
        }

        if future_exog is not None:
            predict_kwargs["X_df"] = future_exog.copy(deep=True)

        before = engine.predict(**predict_kwargs)

        bundle = model_dir / "statsforecast.pkl"

        engine.save(path=bundle)

        result["save_status"] = "VERIFIED" if bundle.is_file() else "FAILED"

        result["bundle_bytes"] = bundle.stat().st_size if bundle.is_file() else 0

        loaded = core_class.load(bundle)

        result["loaded_shape_match"] = loaded.fitted_.shape == engine.fitted_.shape

        loaded_models = [loaded.fitted_[index, 0] for index in range(loaded.fitted_.shape[0])]

        loaded_snapshots = [
            property_snapshot(
                model_name,
                loaded_model,
                parameters,
            )
            for loaded_model in loaded_models
        ]

        result["loaded"] = loaded_snapshots

        result["loaded_match"] = all(
            property_snapshot_passes(snapshot) for snapshot in loaded_snapshots
        )

        after = loaded.predict(**predict_kwargs)

        prediction_evidence = compare_predictions(
            before,
            after,
        )

        result["prediction_parity"] = prediction_evidence

        result["load_status"] = (
            "VERIFIED" if (result["loaded_shape_match"] and result["loaded_match"]) else "FAILED"
        )

        passed = all(
            (
                result["constructed_match"],
                result["fitted_shape_match"],
                result["fitted_match"],
                result["fit_status"] == "VERIFIED",
                result["save_status"] == "VERIFIED",
                result["load_status"] == "VERIFIED",
                prediction_evidence["passed"],
            )
        )

        result["property_status"] = "VERIFIED" if passed else "VALIDATION_FAILED"

    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)

    write_json(
        model_dir / "property_result.json",
        result,
    )

    return result


def certify_property_suite(
    *,
    output_root: Path,
    run_id: str,
    core_class: type,
    models_module: Any,
    horizon: int = 1,
    seed: int = 1,
) -> Path:
    run_dir = output_root / run_id
    run_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    results = []

    for model_name in MODEL_NAMES:
        results.append(
            certify_property_lifecycle(
                run_dir=run_dir,
                model_name=model_name,
                core_class=core_class,
                models_module=models_module,
                horizon=horizon,
                seed=seed,
            )
        )

    verified = sum(result["property_status"] == "VERIFIED" for result in results)

    negative_control = sum(
        result["property_status"] == "EXPECTED_NEGATIVE_CONTROL" for result in results
    )

    validation_failed = sum(result["property_status"] == "VALIDATION_FAILED" for result in results)

    execution_failed = sum(result["property_status"] == "EXECUTION_FAILED" for result in results)

    known = {
        "VERIFIED",
        "EXPECTED_NEGATIVE_CONTROL",
        "VALIDATION_FAILED",
        "EXECUTION_FAILED",
    }

    other_status = sum(result["property_status"] not in known for result in results)

    failed_models = [
        result["model_name"]
        for result in results
        if result["property_status"]
        not in {
            "VERIFIED",
            "EXPECTED_NEGATIVE_CONTROL",
        }
    ]

    formal_pass = bool(
        len(results) == len(MODEL_NAMES)
        and verified == len(MODEL_NAMES) - 1
        and negative_control == 1
        and validation_failed == 0
        and execution_failed == 0
        and other_status == 0
        and not failed_models
    )

    write_json(
        run_dir / "PROPERTY_CERTIFICATION_MATRIX.json",
        results,
    )

    write_json(
        run_dir / "PROPERTY_CERTIFICATION_SUMMARY.json",
        {
            "schema_version": 1,
            "library": "statsforecast",
            "seed": seed,
            "horizon": horizon,
            "model_count": len(results),
            "verified": verified,
            "negative_control": negative_control,
            "validation_failed": validation_failed,
            "execution_failed": execution_failed,
            "other_status": other_status,
            "failed_models": failed_models,
            "formal_pass": formal_pass,
        },
    )

    write_manifest_and_sums(run_dir)

    return run_dir


def main(
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Certify StatsForecast model-property "
            "construction, fit, persistence, and "
            "prediction parity."
        )
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--run-id",
        required=True,
    )

    parser.add_argument(
        "--horizon",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=1,
    )

    args = parser.parse_args(argv)

    from statsforecast import StatsForecast
    from statsforecast import models as models_module

    run_dir = certify_property_suite(
        output_root=args.output_root,
        run_id=args.run_id,
        core_class=StatsForecast,
        models_module=models_module,
        horizon=args.horizon,
        seed=args.seed,
    )

    import json

    report = json.loads(
        (run_dir / "PROPERTY_CERTIFICATION_SUMMARY.json").read_text(encoding="utf-8")
    )

    print(f"RUN_DIR={run_dir}")
    print(f"FORMAL_PASS={str(report['formal_pass']).lower()}")

    return 0 if report["formal_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "certify_property_lifecycle",
    "certify_property_suite",
    "main",
    "normalize_property",
    "property_snapshot",
    "property_snapshot_passes",
]

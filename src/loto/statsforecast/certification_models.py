from __future__ import annotations

import inspect
from copy import deepcopy
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd

from .certification_io import write_json
from .contracts import ExpectedStatus, RuntimeStatus
from .inventory import model_contract
from .runtime import StatsForecastRuntimeAdapter

_DEFAULTS: dict[str, dict[str, Any]] = {
    "AutoMFLES": {
        "test_size": 4,
        "season_length": [4],
        "n_windows": 2,
    },
    "AutoETS": {"season_length": 4},
    "AutoCES": {"season_length": 4},
    "AutoTBATS": {"season_length": [4]},
    "ARIMA": {"order": (1, 0, 0)},
    "AutoRegressive": {"lags": 1},
    "SimpleExponentialSmoothing": {"alpha": 0.3},
    "SeasonalExponentialSmoothing": {"season_length": 4, "alpha": 0.3},
    "SeasonalExponentialSmoothingOptimized": {"season_length": 4},
    "HoltWinters": {"season_length": 4},
    "SeasonalNaive": {"season_length": 4},
    "ConformalSeasonalPool": {"season_length": 4, "n_samples": 200},
    "WindowAverage": {"window_size": 3},
    "SeasonalWindowAverage": {"season_length": 4, "window_size": 2},
    "TSB": {"alpha_d": 0.3, "alpha_p": 0.3},
    "MSTL": {"season_length": [4]},
    "TBATS": {"season_length": [4]},
    "ConstantModel": {"constant": 1.0},
}
_INTERMITTENT = {"ADIDA", "CrostonClassic", "CrostonOptimized", "CrostonSBA", "IMAPA", "TSB"}
_VOLATILE = {"ARCH", "GARCH"}


def build_panel(model_name: str, seed: int = 1, length: int = 96) -> tuple[pd.DataFrame, str]:
    rng = np.random.default_rng(seed)
    frames = []
    if model_name in _INTERMITTENT:
        profile = "intermittent_nonnegative"
    elif model_name in _VOLATILE:
        profile = "stationary_returns"
    else:
        profile = "positive_trend_seasonal"
    for index in range(2):
        ds = np.arange(1, length + 1, dtype=np.int64)
        if profile == "intermittent_nonnegative":
            y = np.zeros(length)
            event_idx = np.arange(index + 2, length, 7 + index)
            y[event_idx] = rng.integers(1, 8, size=len(event_idx))
        elif profile == "stationary_returns":
            y = rng.normal(0.0, 0.8 + 0.1 * np.sin(ds / 6), size=length)
        else:
            y = 12 + index + 0.03 * ds + 1.5 * np.sin(2 * np.pi * ds / 4)
            y = y + rng.normal(0.0, 0.08, size=length)
        frames.append(pd.DataFrame({"unique_id": f"series_{index + 1}", "ds": ds, "y": y}))
    return pd.concat(frames, ignore_index=True), profile


def required_parameters(model_class: type) -> tuple[str, ...]:
    required = []
    for name, parameter in inspect.signature(model_class).parameters.items():
        if name == "self" or parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue
        if parameter.default is inspect.Parameter.empty:
            required.append(name)
    return tuple(required)


def resolve_parameters(
    model_name: str,
    model_class: type,
    overrides: dict[str, Any] | None,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    parameters = deepcopy(_DEFAULTS.get(model_name, {}))
    parameters.update(deepcopy(overrides or {}))
    if model_name == "SklearnModel" and "model" not in parameters:
        from sklearn.linear_model import LinearRegression

        parameters["model"] = LinearRegression()
    fallback = {
        "alpha": 0.3,
        "alpha_d": 0.3,
        "alpha_p": 0.3,
        "constant": 1.0,
        "lags": 1,
        "order": (1, 0, 0),
        "p": 1,
        "q": 1,
        "season_length": 4,
        "window_size": 3,
    }
    required = required_parameters(model_class)
    for name in required:
        if name not in parameters and name in fallback:
            parameters[name] = deepcopy(fallback[name])
    unresolved = tuple(name for name in required if name not in parameters)
    return parameters, unresolved


def _sorted_prediction(frame: pd.DataFrame) -> pd.DataFrame:
    if {"unique_id", "ds"}.issubset(frame.columns):
        return frame.sort_values(["unique_id", "ds"]).reset_index(drop=True)
    return frame.reset_index(drop=True)


def compare_predictions(before: pd.DataFrame, after: pd.DataFrame) -> dict[str, Any]:
    left = _sorted_prediction(before)
    right = _sorted_prediction(after)
    common = [column for column in left.columns if column in right.columns]
    identity = [column for column in ("unique_id", "ds") if column in common]
    values = [column for column in common if column not in {"unique_id", "ds", "cutoff"}]
    identity_equal = bool(identity) and left[identity].equals(right[identity])
    shape_equal = left.shape == right.shape and left.columns.tolist() == right.columns.tolist()
    max_abs_diff = float("inf")
    values_equal = False
    if values and shape_equal:
        left_values = left[values].to_numpy(dtype=float)
        right_values = right[values].to_numpy(dtype=float)
        max_abs_diff = float(np.max(np.abs(left_values - right_values)))
        values_equal = bool(np.allclose(left_values, right_values, rtol=1e-9, atol=1e-10))
    return {
        "passed": shape_equal and identity_equal and values_equal,
        "shape_equal": shape_equal,
        "identity_equal": identity_equal,
        "values_equal": values_equal,
        "max_abs_diff": max_abs_diff,
    }


def certify_model(
    *,
    run_dir: Path,
    model_name: str,
    core_class: type,
    models_module: Any,
    horizon: int,
    seed: int,
    overrides: dict[str, Any] | None,
    lifecycle: bool,
) -> dict[str, Any]:
    started = perf_counter()
    contract = model_contract(model_name)
    result: dict[str, Any] = {
        "model_name": model_name,
        "expected_status": contract.expected_status.value,
        "champion_eligible": contract.champion_eligible,
        "status": RuntimeStatus.EXECUTION_FAILED.value,
        "lifecycle_status": "NOT_RUN",
    }
    model_dir = run_dir / "models" / model_name
    model_dir.mkdir(parents=True, exist_ok=True)
    try:
        model_class = getattr(models_module, model_name)
        parameters, unresolved = resolve_parameters(model_name, model_class, overrides)
        result["required_parameters"] = list(required_parameters(model_class))
        result["unresolved_parameters"] = list(unresolved)
        if unresolved:
            raise ValueError(f"unresolved constructor parameters: {unresolved}")
        panel, profile = build_panel(model_name, seed=seed)
        result["data_profile"] = profile

        future_exog = None

        if model_name == "SklearnModel":
            panel = panel.copy(deep=True)

            # Deterministic exogenous signal independent of y.
            panel["x1"] = np.sin(panel["ds"].to_numpy(dtype=float) / 5.0)

            future_rows = []

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

            future_exog = pd.DataFrame(future_rows)

        adapter = StatsForecastRuntimeAdapter(
            core_class=core_class,
            models_module=models_module,
        )

        prediction, evidence = adapter.forecast(
            panel,
            model_name=model_name,
            freq=1,
            horizon=horizon,
            parameters=parameters,
            levels=None,
            future_exog=future_exog,
        )
        prediction.to_csv(model_dir / "forecast.csv", index=False)
        result.update(
            {
                key: value.value if hasattr(value, "value") else value
                for key, value in evidence.items()
            }
        )
        if result["status"] not in {
            RuntimeStatus.VERIFIED.value,
            RuntimeStatus.EXPECTED_NEGATIVE_PASS.value,
        }:
            raise ValueError(f"forecast validation failed: {result['status']}")
        if lifecycle and contract.expected_status is not ExpectedStatus.EXPECTED_NEGATIVE_PASS:
            model = model_class(**parameters)
            engine = core_class(models=[model], freq=1, n_jobs=1)
            engine.fit(df=panel.copy(deep=True))
            predict_kwargs: dict[str, Any] = {
                "h": horizon,
            }

            if future_exog is not None:
                predict_kwargs["X_df"] = future_exog.copy(deep=True)

            before = engine.predict(**predict_kwargs)
            bundle = model_dir / "statsforecast.pkl"
            engine.save(path=bundle)
            loaded = core_class.load(bundle)
            loaded_predict_kwargs: dict[str, Any] = {
                "h": horizon,
            }

            if future_exog is not None:
                loaded_predict_kwargs["X_df"] = future_exog.copy(deep=True)

            after = loaded.predict(
                **loaded_predict_kwargs,
            )
            before.to_csv(model_dir / "predict_before_save.csv", index=False)
            after.to_csv(model_dir / "predict_after_load.csv", index=False)
            lifecycle_evidence = compare_predictions(before, after)
            result["lifecycle_status"] = "VERIFIED" if lifecycle_evidence["passed"] else "FAILED"
            result["lifecycle_evidence"] = lifecycle_evidence
            if not lifecycle_evidence["passed"]:
                result["status"] = RuntimeStatus.VALIDATION_FAILED.value
        else:
            result["lifecycle_status"] = "EXPECTED_NOT_APPLICABLE"
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)
        if result.get("status") in {
            RuntimeStatus.VERIFIED.value,
            RuntimeStatus.EXPECTED_NEGATIVE_PASS.value,
        }:
            result["status"] = RuntimeStatus.EXECUTION_FAILED.value
    result["duration_seconds"] = perf_counter() - started
    write_json(model_dir / "result.json", result)
    return result

from __future__ import annotations

import hashlib
import importlib
import json
import os
import traceback
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from loto.sktime_campaign.protocol import (
    ProviderRequest,
    ProviderStatus,
    SmokeModelId,
)


@dataclass(frozen=True)
class SmokeModelSpec:
    """Fixed, reviewable constructor plan for one bounded smoke model."""

    model_id: SmokeModelId
    class_path: str
    constructor: dict[str, Any]
    required_distributions: tuple[str, ...]


MODEL_SPECS: dict[SmokeModelId, SmokeModelSpec] = {
    SmokeModelId.NAIVE_LAST: SmokeModelSpec(
        model_id=SmokeModelId.NAIVE_LAST,
        class_path="sktime.forecasting.naive.NaiveForecaster",
        constructor={"strategy": "last"},
        required_distributions=("sktime",),
    ),
    SmokeModelId.POLYNOMIAL_TREND_D1: SmokeModelSpec(
        model_id=SmokeModelId.POLYNOMIAL_TREND_D1,
        class_path="sktime.forecasting.trend.PolynomialTrendForecaster",
        constructor={"degree": 1, "with_intercept": True},
        required_distributions=("sktime", "scikit-learn"),
    ),
    SmokeModelId.EXPONENTIAL_SMOOTHING: SmokeModelSpec(
        model_id=SmokeModelId.EXPONENTIAL_SMOOTHING,
        class_path="sktime.forecasting.exp_smoothing.ExponentialSmoothing",
        constructor={"optimized": True, "use_brute": False},
        required_distributions=("sktime", "statsmodels"),
    ),
    SmokeModelId.THETA: SmokeModelSpec(
        model_id=SmokeModelId.THETA,
        class_path="sktime.forecasting.theta.ThetaForecaster",
        constructor={"deseasonalize": False, "sp": 1},
        required_distributions=("sktime", "statsmodels"),
    ),
}


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _distribution_versions(
    distributions: tuple[str, ...],
) -> tuple[dict[str, str], list[str]]:
    installed: dict[str, str] = {}
    missing: list[str] = []
    for distribution in distributions:
        try:
            installed[distribution] = version(distribution)
        except PackageNotFoundError:
            missing.append(distribution)
    return installed, missing


def _load_class(class_path: str) -> type[Any]:
    module_name, _, class_name = class_path.rpartition(".")
    if not module_name or not class_name:
        raise RuntimeError(f"invalid fixed class path: {class_path}")
    module = importlib.import_module(module_name)
    estimator_class = getattr(module, class_name)
    if not isinstance(estimator_class, type):
        raise TypeError(f"fixed class path did not resolve to a class: {class_path}")
    return estimator_class


def _prediction_values(
    prediction: pd.Series | pd.DataFrame,
    *,
    expected_index: list[int],
) -> np.ndarray:
    if isinstance(prediction, pd.DataFrame):
        if prediction.shape[1] != 1:
            raise RuntimeError(
                "prediction must contain exactly one target column, "
                f"got shape {prediction.shape}"
            )
        values = prediction.iloc[:, 0].to_numpy(dtype=float)
        index = prediction.index
    elif isinstance(prediction, pd.Series):
        values = prediction.to_numpy(dtype=float)
        index = prediction.index
    else:
        raise RuntimeError(
            "prediction type mismatch: expected pandas Series or DataFrame, "
            f"got {type(prediction).__name__}"
        )

    if values.shape != (len(expected_index),):
        raise RuntimeError(
            f"prediction shape mismatch: expected {(len(expected_index),)}, "
            f"got {values.shape}"
        )
    if not np.isfinite(values).all():
        raise RuntimeError("prediction contains NaN or Inf")

    actual_index = [int(value) for value in index.tolist()]
    if actual_index != expected_index:
        raise RuntimeError(
            f"prediction index mismatch: expected {expected_index}, "
            f"got {actual_index}"
        )
    return values


def _phase_defaults() -> dict[str, str]:
    return {
        "dependency_status": "NOT_ATTEMPTED",
        "import_status": "NOT_ATTEMPTED",
        "construct_status": "NOT_ATTEMPTED",
        "fit_status": "NOT_ATTEMPTED",
        "predict_status": "NOT_ATTEMPTED",
        "save_load_status": "NOT_ATTEMPTED",
    }


def _failure(
    *,
    model_id: SmokeModelId,
    spec: SmokeModelSpec,
    phases: dict[str, str],
    phase: str,
    status: ProviderStatus,
    exc: BaseException | None,
    dependency_versions: dict[str, str],
    missing_dependencies: list[str],
    seed: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model_id": model_id.value,
        "class_path": spec.class_path,
        "constructor": spec.constructor,
        "status": status.value,
        "device": "cpu",
        "cpu_fallback": False,
        "pid": os.getpid(),
        "seed": seed,
        "required_distributions": list(spec.required_distributions),
        "dependency_versions": dependency_versions,
        "missing_dependencies": missing_dependencies,
        **phases,
        "failed_phase": phase,
    }
    if exc is not None:
        payload["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
        }
    return payload


def run_model_smoke(
    *,
    model_id: SmokeModelId,
    request: ProviderRequest,
    output_dir: Path,
    specs: Mapping[SmokeModelId, SmokeModelSpec] | None = None,
) -> dict[str, Any]:
    """Execute one fixed smoke model while retaining phase-specific evidence."""

    active_specs = MODEL_SPECS if specs is None else specs
    spec = active_specs[model_id]
    phases = _phase_defaults()

    dependency_versions, missing_dependencies = _distribution_versions(
        spec.required_distributions
    )
    if missing_dependencies:
        phases["dependency_status"] = "UNAVAILABLE"
        return _failure(
            model_id=model_id,
            spec=spec,
            phases=phases,
            phase="dependency",
            status=ProviderStatus.UNAVAILABLE,
            exc=None,
            dependency_versions=dependency_versions,
            missing_dependencies=missing_dependencies,
            seed=request.seed,
        )
    phases["dependency_status"] = "PASS"

    try:
        estimator_class = _load_class(spec.class_path)
        phases["import_status"] = "PASS"
    except Exception as exc:
        phases["import_status"] = "FAILED"
        return _failure(
            model_id=model_id,
            spec=spec,
            phases=phases,
            phase="import",
            status=ProviderStatus.FAILED,
            exc=exc,
            dependency_versions=dependency_versions,
            missing_dependencies=[],
            seed=request.seed,
        )

    try:
        forecaster = estimator_class(**spec.constructor)
        phases["construct_status"] = "PASS"
    except Exception as exc:
        phases["construct_status"] = "FAILED"
        return _failure(
            model_id=model_id,
            spec=spec,
            phases=phases,
            phase="construct",
            status=ProviderStatus.FAILED,
            exc=exc,
            dependency_versions=dependency_versions,
            missing_dependencies=[],
            seed=request.seed,
        )

    target = pd.Series(
        request.series,
        index=pd.RangeIndex(
            start=1,
            stop=len(request.series) + 1,
            step=1,
            name="draw_no",
        ),
        name="y",
        dtype=float,
    )
    expected_index = [len(target) + step for step in request.forecast_horizon]

    try:
        forecaster.fit(target, fh=request.forecast_horizon)
        phases["fit_status"] = "PASS"
    except Exception as exc:
        phases["fit_status"] = "FAILED"
        return _failure(
            model_id=model_id,
            spec=spec,
            phases=phases,
            phase="fit",
            status=ProviderStatus.FAILED,
            exc=exc,
            dependency_versions=dependency_versions,
            missing_dependencies=[],
            seed=request.seed,
        )

    try:
        prediction = forecaster.predict(fh=request.forecast_horizon)
        values_before = _prediction_values(
            prediction,
            expected_index=expected_index,
        )
        phases["predict_status"] = "PASS"
    except Exception as exc:
        phases["predict_status"] = "FAILED"
        return _failure(
            model_id=model_id,
            spec=spec,
            phases=phases,
            phase="predict",
            status=ProviderStatus.FAILED,
            exc=exc,
            dependency_versions=dependency_versions,
            missing_dependencies=[],
            seed=request.seed,
        )

    save_load: dict[str, Any] = {"requested": request.save_load}
    values_after = values_before.copy()
    if request.save_load:
        try:
            model_base = output_dir / f"{model_id.value}_model"
            archive_handle = forecaster.save(model_base)
            close = getattr(archive_handle, "close", None)
            if callable(close):
                close()
            model_archive = output_dir / f"{model_id.value}_model.zip"
            if not model_archive.is_file() or model_archive.stat().st_size <= 0:
                raise RuntimeError("save did not create a non-empty ZIP artifact")
            loaded = type(forecaster).load_from_path(model_archive)
            prediction_after = loaded.predict(fh=request.forecast_horizon)
            values_after = _prediction_values(
                prediction_after,
                expected_index=expected_index,
            )
            if not np.array_equal(values_before, values_after):
                raise RuntimeError("save/load/re-predict values changed")
            phases["save_load_status"] = "PASS"
            save_load = {
                "requested": True,
                "status": "PASS",
                "artifact": model_archive.name,
                "artifact_sha256": _sha256(model_archive),
                "exact_prediction_match": True,
            }
        except Exception as exc:
            phases["save_load_status"] = "FAILED"
            return _failure(
                model_id=model_id,
                spec=spec,
                phases=phases,
                phase="save_load",
                status=ProviderStatus.FAILED,
                exc=exc,
                dependency_versions=dependency_versions,
                missing_dependencies=[],
                seed=request.seed,
            )
    else:
        phases["save_load_status"] = "NOT_REQUESTED"

    tags = forecaster.get_tags()
    selected_tags = {
        key: tags.get(key)
        for key in (
            "capability:missing_values",
            "capability:pred_int",
            "property:randomness",
            "python_dependencies",
            "requires-fh-in-fit",
        )
        if key in tags
    }

    return {
        "model_id": model_id.value,
        "class_path": spec.class_path,
        "constructor": spec.constructor,
        "status": ProviderStatus.PASS.value,
        "device": "cpu",
        "cpu_fallback": False,
        "pid": os.getpid(),
        "seed": request.seed,
        "required_distributions": list(spec.required_distributions),
        "dependency_versions": dependency_versions,
        "missing_dependencies": [],
        **phases,
        "input_rows": len(target),
        "input_index_kind": "RangeIndex",
        "forecast_horizon": request.forecast_horizon,
        "expected_prediction_index": expected_index,
        "prediction_shape": list(values_before.shape),
        "prediction_finite": True,
        "prediction_before_save": values_before.tolist(),
        "prediction_after_load": values_after.tolist(),
        "save_load": save_load,
        "instance_tags": selected_tags,
    }


def summarize_matrix_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute a fail-closed aggregate without hiding per-model failures."""

    counts = {
        status.value: sum(row.get("status") == status.value for row in results)
        for status in ProviderStatus
    }
    total = len(results)
    if counts[ProviderStatus.PASS.value] == total and total > 0:
        overall = ProviderStatus.PASS
    elif counts[ProviderStatus.PASS.value] > 0:
        overall = ProviderStatus.PARTIAL
    elif counts[ProviderStatus.UNAVAILABLE.value] == total and total > 0:
        overall = ProviderStatus.UNAVAILABLE
    else:
        overall = ProviderStatus.FAILED

    return {
        "status": overall.value,
        "total": total,
        "counts": counts,
        "all_requested_models_passed": overall is ProviderStatus.PASS,
    }


def run_smoke_matrix(
    request: ProviderRequest,
    output_dir: Path,
    *,
    specs: Mapping[SmokeModelId, SmokeModelSpec] | None = None,
) -> dict[str, Any]:
    """Run every requested fixed model and continue after individual failures."""

    np.random.seed(request.seed)
    input_contract = {
        "series_rows": len(request.series),
        "series_sha256": _canonical_sha256(request.series),
        "forecast_horizon": request.forecast_horizon,
        "forecast_horizon_sha256": _canonical_sha256(request.forecast_horizon),
    }
    results = [
        run_model_smoke(
            model_id=model_id,
            request=request,
            output_dir=output_dir,
            specs=specs,
        )
        for model_id in request.model_ids
    ]
    summary = summarize_matrix_results(results)
    return {
        "schema_version": "1.0",
        "status": summary["status"],
        "device": "cpu",
        "cpu_fallback": False,
        "pid": os.getpid(),
        "seed": request.seed,
        "input_contract": input_contract,
        "thread_limits": {
            name: os.environ.get(name)
            for name in (
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
        "requested_model_ids": [model_id.value for model_id in request.model_ids],
        "summary": summary,
        "results": results,
    }

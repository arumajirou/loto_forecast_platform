from __future__ import annotations

# ruff: noqa: E501
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.data.canonical import canonicalize_loto7
from loto.data.lineage import atomic_write_json
from loto.evaluation.metrics import brier_score, log_loss
from loto.features.pipeline import build_candidate_features, build_next_candidate_features
from loto.models.argument_verifier import verify_arguments
from loto.models.artifact_store import load_pickle_model, model_manifest
from loto.models.catalog import ModelSpec
from loto.models.factory import RuntimeModel
from loto.models.property_inspector import inspect_model_properties
from loto.observability.gpu import collect_gpu_evidence

FINAL_STATUSES = {
    "PASS",
    "ZERO_SHOT_PASS",
    "FIT_FAILED",
    "RETRAIN_FAILED",
    "PREDICT_FAILED",
    "SAVE_FAILED",
    "LOAD_FAILED",
    "RELOADED_PREDICT_FAILED",
    "PREDICTION_MISMATCH",
    "INVALID_PREDICTION",
    "PROPERTY_INSPECTION_FAILED",
    "ARGUMENT_NOT_APPLIED",
    "GPU_NOT_USED",
    "GPU_PARTIAL",
    "CPU_FALLBACK",
    "CUDA_OOM",
    "DEPENDENCY_MISSING",
    "BACKEND_UNAVAILABLE",
    "HIERARCHY_INVALID",
    "UNSUPPORTED_DATA_HIERARCHY",
    "CLASS_MISSING",
    "WORKER_NOT_IMPLEMENTED",
    "PROVIDER_NOT_IMPLEMENTED",
    "VERSION_INCOMPATIBLE",
    "UNSUPPORTED_OPERATION",
    "TIMEOUT",
    "ARTIFACT_MISSING",
}


@dataclass
class ModelLifecycleResult:
    model_id: str
    fit_status: str
    predict_status: str
    save_status: str
    load_status: str
    retrain_status: str
    model_artifact: Path | None
    predictions: np.ndarray
    reloaded_predictions: np.ndarray | None
    retrained_predictions: np.ndarray | None
    properties_before: dict[str, Any]
    properties_after_fit: dict[str, Any]
    properties_after_load: dict[str, Any]
    properties_after_retrain: dict[str, Any]
    argument_evidence: list[dict[str, Any]]
    resource_evidence: dict[str, Any]
    errors: list[dict[str, Any]] = field(default_factory=list)
    final_status: str = "UNSUPPORTED_OPERATION"
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["model_artifact"] = None if self.model_artifact is None else str(self.model_artifact)
        for key in ("predictions", "reloaded_predictions", "retrained_predictions"):
            value = getattr(self, key)
            payload[key] = None if value is None else np.asarray(value).tolist()
        return payload


def validate_prediction(values: np.ndarray, *, expected_shape: tuple[int, ...]) -> None:
    arr = np.asarray(values, dtype=float)
    if arr.shape != expected_shape:
        raise ValueError(f"prediction shape mismatch: expected={expected_shape}, actual={arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("prediction contains NaN or Inf")


def candidate_metrics(actual_numbers: list[int], probabilities: np.ndarray, *, elapsed_seconds: float) -> dict[str, Any]:
    target = np.zeros(37, dtype=float)
    target[np.asarray(actual_numbers, dtype=int) - 1] = 1.0
    clipped = np.clip(np.asarray(probabilities, dtype=float), 1e-9, 1.0 - 1e-9)
    err = clipped - target
    ranked = np.argsort(-clipped)[:7] + 1
    hits = len(set(ranked.tolist()) & set(actual_numbers))
    return {
        "MAE": float(np.mean(np.abs(err))),
        "MSE": float(np.mean(err * err)),
        "RMSE": float(math.sqrt(float(np.mean(err * err)))),
        "median_absolute_error": float(np.median(np.abs(err))),
        "hits_at_7": int(hits),
        "prediction_time_seconds": elapsed_seconds,
        "brier": brier_score(target.reshape(1, -1), clipped.reshape(1, -1)),
        "log_loss": log_loss(target.reshape(1, -1), clipped.reshape(1, -1)),
    }


def run_candidate_lifecycle(
    spec: ModelSpec,
    master: pd.DataFrame,
    *,
    params: dict[str, Any],
    seed: int,
    output_dir: Path,
    windows: tuple[int, ...] = (5, 10, 20),
    tolerance: float = 1e-10,
    device: str = "cpu",
    precision: str = "32",
) -> ModelLifecycleResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    if "draw_id" not in master.columns or "available_at" not in master.columns:
        master, _manifest = canonicalize_loto7(master, source="lifecycle")
    requested = spec.default_params | params | {"seed": seed, "device": device, "precision": precision}
    train = build_candidate_features(master.iloc[:-1].copy(), windows=windows)
    query = build_next_candidate_features(master.iloc[:-1].copy(), windows=windows)
    actual = [int(master.iloc[-1][f"n{i}"]) for i in range(1, 8)]
    before = inspect_model_properties(spec, None, params=requested, device=device, precision=precision)
    errors: list[dict[str, Any]] = []
    resource_before = collect_gpu_evidence(gpu_required=False)
    model_artifact: Path | None = None
    predictions = np.asarray([], dtype=float)
    reloaded_predictions: np.ndarray | None = None
    retrained_predictions: np.ndarray | None = None
    properties_after_fit: dict[str, Any] = {}
    properties_after_load: dict[str, Any] = {}
    properties_after_retrain: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    fit_status = predict_status = save_status = load_status = retrain_status = "NOT_RUN"
    final_status = "UNSUPPORTED_OPERATION"
    try:
        started = time.perf_counter()
        runtime = RuntimeModel(spec, params, seed=seed).fit_candidate(train)
        fit_elapsed = time.perf_counter() - started
        fit_status = "OK"
        properties_after_fit = inspect_model_properties(spec, runtime.model, params=requested, device=device, precision=precision)
        started = time.perf_counter()
        output = runtime.predict_candidate(query)
        pred_elapsed = time.perf_counter() - started
        predictions = np.asarray(output.candidate_probabilities, dtype=float)
        validate_prediction(predictions, expected_shape=(37,))
        predict_status = "OK"
        metrics = candidate_metrics(actual, predictions, elapsed_seconds=pred_elapsed)
        metrics["training_time_seconds"] = fit_elapsed
    except Exception as exc:
        errors.append({"stage": "fit_predict", "type": type(exc).__name__, "message": str(exc)})
        final_status = "FIT_FAILED" if fit_status != "OK" else "PREDICT_FAILED"
    if fit_status == "OK" and predict_status == "OK":
        try:
            model_artifact = runtime.save(output_dir / "model.pkl")
            save_status = "OK"
        except Exception as exc:
            errors.append({"stage": "save", "type": type(exc).__name__, "message": str(exc)})
            save_status = "FAILED"
            final_status = "SAVE_FAILED"
    if model_artifact is not None:
        try:
            reloaded = load_pickle_model(model_artifact)
            loaded_runtime = RuntimeModel(spec, reloaded["params"], seed=int(reloaded["seed"]))
            loaded_runtime.feature_columns = list(reloaded["feature_columns"])
            loaded_runtime.model = reloaded["model"]
            reloaded_predictions = np.asarray(loaded_runtime.predict_candidate(query).candidate_probabilities, dtype=float)
            validate_prediction(reloaded_predictions, expected_shape=(37,))
            if not np.allclose(predictions, reloaded_predictions, atol=tolerance, rtol=0.0):
                final_status = "PREDICTION_MISMATCH"
            load_status = "OK"
            properties_after_load = inspect_model_properties(
                spec, loaded_runtime.model, params=requested, artifact_path=model_artifact, device=device, precision=precision
            )
        except Exception as exc:
            errors.append({"stage": "load_predict", "type": type(exc).__name__, "message": str(exc)})
            load_status = "FAILED"
            final_status = "LOAD_FAILED"
    if load_status == "OK":
        try:
            retrain_master = master.copy()
            retrain = build_candidate_features(retrain_master, windows=windows)
            retrain_query = build_next_candidate_features(retrain_master, windows=windows)
            started = time.perf_counter()
            retrained = RuntimeModel(spec, params, seed=seed).fit_candidate(retrain)
            retrain_elapsed = time.perf_counter() - started
            retrained_predictions = np.asarray(retrained.predict_candidate(retrain_query).candidate_probabilities, dtype=float)
            validate_prediction(retrained_predictions, expected_shape=(37,))
            retrain_status = "OK"
            metrics["retraining_time_seconds"] = retrain_elapsed
            properties_after_retrain = inspect_model_properties(spec, retrained.model, params=requested, device=device, precision=precision)
        except Exception as exc:
            errors.append({"stage": "retrain", "type": type(exc).__name__, "message": str(exc)})
            retrain_status = "FAILED"
            final_status = "RETRAIN_FAILED"
    argument_evidence = verify_arguments(requested, requested, properties_after_fit or before)
    if final_status == "UNSUPPORTED_OPERATION":
        bad_args = [row for row in argument_evidence if row["status"] in {"IGNORED"}]
        if bad_args:
            final_status = "ARGUMENT_NOT_APPLIED"
        elif all(status == "OK" for status in (fit_status, predict_status, save_status, load_status, retrain_status)):
            final_status = "PASS"
    resource_after = collect_gpu_evidence(gpu_required=False)
    resource_evidence = {"before": resource_before, "after": resource_after}
    if model_artifact is not None:
        manifest = model_manifest(
            model_artifact,
            model_id=spec.model_id,
            library=spec.library,
            library_version=properties_after_load.get("library_version"),
            load_test_status=load_status,
            prediction_test_status=predict_status,
        )
        atomic_write_json(output_dir / "model_manifest.json", manifest)
    result = ModelLifecycleResult(
        model_id=spec.model_id,
        fit_status=fit_status,
        predict_status=predict_status,
        save_status=save_status,
        load_status=load_status,
        retrain_status=retrain_status,
        model_artifact=model_artifact,
        predictions=predictions,
        reloaded_predictions=reloaded_predictions,
        retrained_predictions=retrained_predictions,
        properties_before=before,
        properties_after_fit=properties_after_fit,
        properties_after_load=properties_after_load,
        properties_after_retrain=properties_after_retrain,
        argument_evidence=argument_evidence,
        resource_evidence=resource_evidence,
        errors=errors,
        final_status=final_status,
        metrics=metrics,
    )
    atomic_write_json(output_dir / "lifecycle_result.json", result.to_dict())
    return result

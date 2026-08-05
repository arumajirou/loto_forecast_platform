"""Runtime certification for saved NeuralForecast model bundles.

A training call is not considered runtime-certified merely because ``fit`` and
``predict`` returned. Certification saves the fitted bundle, reloads it,
repeats inference, checks finite values and prediction stability, and records
CPU/GPU execution evidence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.auto_campaign.runtime import gpu_process_snapshot, torch_runtime_snapshot


def _point_column(prediction: pd.DataFrame, alias: str) -> str:
    ignored = {"unique_id", "ds", "cutoff"}
    candidates = [column for column in prediction.columns if column not in ignored]
    if alias in candidates:
        return alias
    point_candidates = [
        column
        for column in candidates
        if not any(
            marker in str(column).lower() for marker in ("-lo-", "-hi-", "median", "quantile")
        )
    ]
    if point_candidates:
        return str(point_candidates[0])
    if not candidates:
        raise ValueError("NeuralForecast.predict returned no forecast value columns")
    return str(candidates[0])


def _state_dict_finite(model: Any | None) -> bool:
    if model is None:
        return False
    state_dict = getattr(model, "state_dict", None)
    if not callable(state_dict):
        return False
    state = state_dict()
    if not state:
        return False
    for value in state.values():
        try:
            array = value.detach().cpu().numpy()
        except AttributeError:
            array = np.asarray(value)
        if not np.isfinite(array).all():
            return False
    return True


def _fitted_inner_model(neuralforecast: Any) -> Any | None:
    models = getattr(neuralforecast, "models", None)
    if not models or len(models) != 1:
        return None
    return getattr(models[0], "model", models[0])


def _safe_gpu_process_snapshot() -> dict[str, Any]:
    try:
        return gpu_process_snapshot()
    except FileNotFoundError:
        return {
            "pid": None,
            "returncode": 127,
            "gpu_pid_verified": False,
            "rows": [],
            "error": "nvidia-smi not found",
        }


def certify_saved_runtime(
    *,
    neuralforecast: Any,
    neuralforecast_class: type,
    model_path: Path,
    prediction_before: pd.DataFrame,
    alias: str,
    verbose: bool,
    require_gpu: bool,
) -> dict[str, Any]:
    """Save, reload and verify a fitted NeuralForecast instance.

    Args:
        neuralforecast: Fitted ``NeuralForecast`` instance.
        neuralforecast_class: Class exposing ``load``.
        model_path: Bundle directory passed to ``save`` and ``load``.
        prediction_before: Prediction frame produced before saving.
        alias: Expected point-prediction column alias.
        verbose: Forwarded to the post-load ``predict`` call.
        require_gpu: Fail certification when CUDA execution evidence is absent.

    Returns:
        JSON-serializable certification evidence.

    Raises:
        RuntimeError: When reload, inference, finite-state, prediction equality,
            or required GPU execution cannot be certified.
    """

    before_point = _point_column(prediction_before, alias)
    before_values = prediction_before[before_point].to_numpy(dtype=float)
    if not np.isfinite(before_values).all():
        raise RuntimeError("pre-save prediction contains non-finite values")

    fitted_model = _fitted_inner_model(neuralforecast)
    state_before_finite = _state_dict_finite(fitted_model)
    if not state_before_finite:
        raise RuntimeError("pre-save fitted state_dict is missing or non-finite")

    runtime_before = torch_runtime_snapshot(fitted_model)
    gpu_before = _safe_gpu_process_snapshot()

    neuralforecast.save(str(model_path), save_dataset=True, overwrite=True)
    loaded = neuralforecast_class.load(str(model_path))
    prediction_after = loaded.predict(verbose=verbose)
    after_point = _point_column(prediction_after, alias)
    after_values = prediction_after[after_point].to_numpy(dtype=float)

    loaded_model = _fitted_inner_model(loaded)
    state_after_finite = _state_dict_finite(loaded_model)
    runtime_after = torch_runtime_snapshot(loaded_model)
    gpu_after = _safe_gpu_process_snapshot()

    shape_match = before_values.shape == after_values.shape
    finite = bool(np.isfinite(after_values).all())
    prediction_match = bool(
        shape_match
        and np.allclose(before_values, after_values, rtol=1e-6, atol=1e-6)
    )
    max_abs_diff = (
        float(np.max(np.abs(before_values - after_values)))
        if shape_match and before_values.size
        else None
    )
    cuda_execution_evidence = bool(
        str(runtime_before.get("trainer_root_device", "")).startswith("cuda")
        or str(runtime_after.get("trainer_root_device", "")).startswith("cuda")
        or runtime_before.get("cuda_peak_memory_allocated", 0) > 0
        or runtime_after.get("cuda_peak_memory_allocated", 0) > 0
        or gpu_before.get("gpu_pid_verified")
        or gpu_after.get("gpu_pid_verified")
    )
    cpu_fallback = bool(require_gpu and not cuda_execution_evidence)

    result = {
        "status": "PASS",
        "loaded": True,
        "predicted": True,
        "shape_match": shape_match,
        "finite": finite,
        "prediction_match": prediction_match,
        "max_abs_diff": max_abs_diff,
        "state_before_finite": state_before_finite,
        "state_after_finite": state_after_finite,
        "require_gpu": require_gpu,
        "cuda_execution_evidence": cuda_execution_evidence,
        "cpu_fallback": cpu_fallback,
        "runtime_before": runtime_before,
        "runtime_after": runtime_after,
        "gpu_before": gpu_before,
        "gpu_after": gpu_after,
        "point_column_before": before_point,
        "point_column_after": after_point,
    }
    if not (
        shape_match
        and finite
        and prediction_match
        and state_before_finite
        and state_after_finite
        and not cpu_fallback
    ):
        result["status"] = "FAIL"
        raise RuntimeError(f"NeuralForecast runtime certification failed: {result}")

    prediction_after.to_csv(model_path.parent / "prediction_after_load.csv", index=False)
    return result

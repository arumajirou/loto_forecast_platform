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


def _runtime_has_cuda_evidence(snapshot: dict[str, Any]) -> bool:
    return bool(
        str(snapshot.get("parameter_device", "")).startswith("cuda")
        or str(snapshot.get("trainer_root_device", "")).startswith("cuda")
        or snapshot.get("cuda_memory_allocated", 0) > 0
        or snapshot.get("cuda_memory_reserved", 0) > 0
        or snapshot.get("cuda_peak_memory_allocated", 0) > 0
    )


def _key_frames_match(
    before: pd.DataFrame,
    after: pd.DataFrame,
    key_columns: list[str],
) -> bool:
    if len(before) != len(after):
        return False
    try:
        pd.testing.assert_frame_equal(
            before[key_columns],
            after[key_columns],
            check_dtype=False,
            check_exact=True,
        )
    except AssertionError:
        return False
    return True


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

    The function always returns structured evidence. A failed check or an
    exception produces ``status=FAIL`` so the caller can persist the evidence
    before failing the model task.
    """

    result: dict[str, Any] = {
        "status": "FAIL",
        "failed_phase": "pre_save_validation",
        "loaded": False,
        "predicted": False,
        "shape_match": False,
        "key_match": False,
        "finite": False,
        "prediction_match": False,
        "max_abs_diff": None,
        "state_before_finite": False,
        "state_after_finite": False,
        "require_gpu": require_gpu,
        "cuda_execution_evidence": False,
        "cpu_fallback": require_gpu,
        "runtime_before": {},
        "runtime_after": {},
        "gpu_before": {},
        "gpu_after": {},
        "point_column_before": None,
        "point_column_after": None,
        "key_columns": ["unique_id", "ds"],
        "duplicate_keys_before": False,
        "duplicate_keys_after": False,
        "failed_checks": [],
    }

    try:
        key_columns = list(result["key_columns"])
        missing_before = [column for column in key_columns if column not in prediction_before]
        if missing_before:
            result["failed_checks"] = ["prediction_keys_before"]
            result["error"] = f"pre-save prediction is missing keys: {missing_before}"
            return result

        before_point = _point_column(prediction_before, alias)
        result["point_column_before"] = before_point
        before_frame = prediction_before[[*key_columns, before_point]].copy()
        result["duplicate_keys_before"] = bool(before_frame.duplicated(key_columns).any())
        before_frame = before_frame.sort_values(key_columns, kind="stable").reset_index(drop=True)
        before_values = before_frame[before_point].to_numpy(dtype=float)
        finite_before = bool(np.isfinite(before_values).all())

        fitted_model = _fitted_inner_model(neuralforecast)
        state_before_finite = _state_dict_finite(fitted_model)
        runtime_before = torch_runtime_snapshot(fitted_model)
        gpu_before = _safe_gpu_process_snapshot()
        result.update(
            {
                "state_before_finite": state_before_finite,
                "runtime_before": runtime_before,
                "gpu_before": gpu_before,
            }
        )

        pre_save_failures: list[str] = []
        if not finite_before:
            pre_save_failures.append("finite_predictions_before")
        if not state_before_finite:
            pre_save_failures.append("finite_state_dict_before")
        if result["duplicate_keys_before"]:
            pre_save_failures.append("unique_prediction_keys_before")
        if pre_save_failures:
            result["failed_checks"] = pre_save_failures
            result["error"] = "pre-save runtime certification checks failed"
            return result

        result["failed_phase"] = "save"
        neuralforecast.save(str(model_path), save_dataset=True, overwrite=True)

        result["failed_phase"] = "load"
        loaded = neuralforecast_class.load(str(model_path))
        result["loaded"] = True

        result["failed_phase"] = "predict_after_load"
        prediction_after = loaded.predict(verbose=verbose)
        result["predicted"] = True
        prediction_after.to_csv(model_path.parent / "prediction_after_load.csv", index=False)

        missing_after = [column for column in key_columns if column not in prediction_after]
        if missing_after:
            result["failed_checks"] = ["prediction_keys_after"]
            result["error"] = f"post-load prediction is missing keys: {missing_after}"
            return result

        after_point = _point_column(prediction_after, alias)
        result["point_column_after"] = after_point
        after_frame = prediction_after[[*key_columns, after_point]].copy()
        result["duplicate_keys_after"] = bool(after_frame.duplicated(key_columns).any())
        after_frame = after_frame.sort_values(key_columns, kind="stable").reset_index(drop=True)
        after_values = after_frame[after_point].to_numpy(dtype=float)

        loaded_model = _fitted_inner_model(loaded)
        state_after_finite = _state_dict_finite(loaded_model)
        runtime_after = torch_runtime_snapshot(loaded_model)
        gpu_after = _safe_gpu_process_snapshot()

        shape_match = before_values.shape == after_values.shape
        key_match = _key_frames_match(before_frame, after_frame, key_columns)
        finite_after = bool(np.isfinite(after_values).all())
        prediction_match = bool(
            key_match
            and shape_match
            and np.allclose(before_values, after_values, rtol=1e-6, atol=1e-6)
        )
        max_abs_diff = (
            float(np.max(np.abs(before_values - after_values)))
            if key_match and shape_match and before_values.size
            else None
        )
        cuda_execution_evidence = bool(
            _runtime_has_cuda_evidence(runtime_before)
            or _runtime_has_cuda_evidence(runtime_after)
            or gpu_before.get("gpu_pid_verified")
            or gpu_after.get("gpu_pid_verified")
        )
        cpu_fallback = bool(require_gpu and not cuda_execution_evidence)

        failed_checks: list[str] = []
        if not shape_match:
            failed_checks.append("prediction_shape_match")
        if not key_match:
            failed_checks.append("prediction_key_match")
        if not finite_after:
            failed_checks.append("finite_predictions_after")
        if not prediction_match:
            failed_checks.append("prediction_value_match")
        if not state_after_finite:
            failed_checks.append("finite_state_dict_after")
        if result["duplicate_keys_after"]:
            failed_checks.append("unique_prediction_keys_after")
        if cpu_fallback:
            failed_checks.append("no_cpu_fallback")

        result.update(
            {
                "status": "PASS" if not failed_checks else "FAIL",
                "failed_phase": None if not failed_checks else "verification",
                "shape_match": shape_match,
                "key_match": key_match,
                "finite": finite_after,
                "prediction_match": prediction_match,
                "max_abs_diff": max_abs_diff,
                "state_after_finite": state_after_finite,
                "cuda_execution_evidence": cuda_execution_evidence,
                "cpu_fallback": cpu_fallback,
                "runtime_after": runtime_after,
                "gpu_after": gpu_after,
                "failed_checks": failed_checks,
            }
        )
        return result
    except Exception as exc:
        result.update(
            {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )
        return result

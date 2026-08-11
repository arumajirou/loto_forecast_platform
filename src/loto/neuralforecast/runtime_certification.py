"""Save/load runtime certification for NeuralForecast model bundles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.data.lineage import atomic_write_json

from .runtime_compare import compare_predictions
from .runtime_evidence import (
    cuda_phase_baseline,
    cuda_phase_evidence,
    extract_training_evidence,
    fitted_inner_model,
    formal_training_cuda,
    state_dict_finite,
    torch_runtime_snapshot,
)
from .runtime_evidence import (
    safe_gpu_process_snapshot as _safe_gpu_process_snapshot,
)
from .runtime_policy import (
    PredictionComparisonPolicy,
    precision_tolerance,
    resolve_prediction_policy,
    seed_runtime,
)
from .runtime_prediction import (
    collect_prediction_samples,
    key_frames_match,
    prediction_frame,
)


class RuntimeCertificationFailure(RuntimeError):
    """Raised only after structured certification evidence is durable."""


def _finish_result(model_path: Path, result: dict[str, Any]) -> dict[str, Any]:
    evidence_path = model_path.parent / "runtime_certification.json"
    result["evidence_path"] = str(evidence_path)
    atomic_write_json(evidence_path, result)
    if result.get("status") != "PASS":
        raise RuntimeCertificationFailure(
            "NeuralForecast runtime certification failed; "
            f"evidence={evidence_path}; failed_checks={result.get('failed_checks', [])}"
        )
    return result


def _initial_result(
    *,
    policy: PredictionComparisonPolicy,
    random_seed: int,
    precision: str | None,
    stochastic_samples: int,
    require_gpu: bool,
    training_evidence: dict[str, Any] | None,
    rtol: float,
    atol: float,
) -> dict[str, Any]:
    return {
        "schema_version": "1.3.0",
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
        "prediction_policy": policy,
        "random_seed": random_seed,
        "precision": precision or "32-true",
        "comparison_rtol": rtol,
        "comparison_atol": atol,
        "stochastic_samples": stochastic_samples if policy == "stochastic" else 1,
        "require_gpu": require_gpu,
        "training_evidence": training_evidence or {},
        # Kept for compatibility. This is pre-save inference evidence, not training proof.
        "cuda_training_evidence": False,
        "formal_cuda_training_evidence": False,
        "cuda_pre_save_inference_evidence": False,
        "cuda_reload_inference_evidence": False,
        "cuda_execution_evidence": False,
        "cpu_fallback": require_gpu,
        "runtime_pre_save_inference": {},
        "runtime_reload_inference": {},
        "gpu_pre_save_inference": {},
        "gpu_reload_inference": {},
        "cuda_pre_save_phase_baseline": {},
        "cuda_pre_save_phase_evidence": {},
        "cuda_reload_phase_baseline": {},
        "cuda_reload_phase_evidence": {},
        "point_column_before": None,
        "point_column_after": None,
        "key_columns": ["unique_id", "ds"],
        "duplicate_keys_before": False,
        "duplicate_keys_after": False,
        "prediction_comparison": {},
        "failed_checks": [],
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
    prediction_policy: PredictionComparisonPolicy | None = None,
    random_seed: int = 1,
    precision: str | None = None,
    stochastic_samples: int = 5,
    training_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist, reload, infer, and fail closed with durable evidence.

    Deterministic models compare point values with precision-aware tolerances.
    Stochastic models compare the mean and standard deviation of explicitly
    seeded samples. Formal GPU certification requires trial/worker training
    proof plus independent pre-save and reload-inference CUDA evidence.

    Process-local inference CUDA evidence is phase-bound: immediately before
    each prediction phase the PyTorch peak counter is reset and its allocated
    byte baseline is captured. The phase passes only when the post-prediction
    peak rises above that baseline (or an external nvidia-smi PID match exists).
    """

    policy = resolve_prediction_policy(neuralforecast, prediction_policy)
    if policy == "stochastic" and stochastic_samples < 2:
        raise ValueError("stochastic_samples must be >= 2 for stochastic comparison")
    base_rtol, base_atol = precision_tolerance(precision)
    rtol = max(base_rtol, 5e-2) if policy == "stochastic" else base_rtol
    atol = max(base_atol, 5e-2) if policy == "stochastic" else base_atol
    model_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_training = training_evidence or extract_training_evidence(neuralforecast)
    result = _initial_result(
        policy=policy,
        random_seed=random_seed,
        precision=precision,
        stochastic_samples=stochastic_samples,
        require_gpu=require_gpu,
        training_evidence=resolved_training,
        rtol=rtol,
        atol=atol,
    )

    try:
        before_frame, before_point, initial_values, initial_duplicate = prediction_frame(
            prediction_before,
            alias,
        )
        result["point_column_before"] = before_point
        result["duplicate_keys_before"] = initial_duplicate
        fitted_model = fitted_inner_model(neuralforecast)
        result["state_before_finite"] = state_dict_finite(fitted_model)

        pre_failures: list[str] = []
        if not np.isfinite(initial_values).all():
            pre_failures.append("finite_predictions_before")
        if not result["state_before_finite"]:
            pre_failures.append("finite_state_dict_before")
        if initial_duplicate:
            pre_failures.append("unique_prediction_keys_before")
        if pre_failures:
            result["failed_checks"] = pre_failures
            result["error"] = "pre-save runtime certification checks failed"
            return _finish_result(model_path, result)

        pre_phase_baseline = cuda_phase_baseline() if require_gpu else {}
        result["cuda_pre_save_phase_baseline"] = pre_phase_baseline

        if policy == "stochastic":
            (
                before_samples,
                before_point,
                before_values,
                before_duplicate,
                before_keys_consistent,
            ) = collect_prediction_samples(
                neuralforecast,
                alias=alias,
                verbose=verbose,
                random_seed=random_seed,
                sample_count=stochastic_samples,
            )
            result["duplicate_keys_before"] = bool(initial_duplicate or before_duplicate)
            pd.concat(before_samples, ignore_index=True).to_csv(
                model_path.parent / "prediction_samples_before_save.csv",
                index=False,
            )
            before_reference = before_samples[0].drop(columns=["sample_index", "seed"])
            before_reference = before_reference.rename(columns={"prediction": before_point})
        elif require_gpu:
            seed_runtime(random_seed)
            prediction_probe = neuralforecast.predict(verbose=verbose)
            prediction_probe.to_csv(model_path.parent / "prediction_before_save.csv", index=False)
            before_frame, before_point, before_vector, before_duplicate = prediction_frame(
                prediction_probe,
                alias,
            )
            before_values = before_vector.reshape(1, -1)
            before_keys_consistent = True
            before_reference = before_frame
            result["duplicate_keys_before"] = bool(initial_duplicate or before_duplicate)
            result["point_column_before"] = before_point
        else:
            before_values = initial_values.reshape(1, -1)
            before_keys_consistent = True
            before_reference = before_frame

        runtime_pre = torch_runtime_snapshot(fitted_model)
        gpu_pre = _safe_gpu_process_snapshot()
        pre_phase = cuda_phase_evidence(
            runtime_pre,
            gpu_pre,
            pre_phase_baseline if require_gpu else None,
        )
        pre_cuda = bool(pre_phase["verified"])
        result.update(
            {
                "runtime_pre_save_inference": runtime_pre,
                "gpu_pre_save_inference": gpu_pre,
                "cuda_pre_save_phase_evidence": pre_phase,
                "cuda_pre_save_inference_evidence": pre_cuda,
                "cuda_training_evidence": pre_cuda,
                "formal_cuda_training_evidence": formal_training_cuda(resolved_training),
            }
        )

        result["failed_phase"] = "save"
        neuralforecast.save(str(model_path), save_dataset=True, overwrite=True)
        result["failed_phase"] = "load"
        loaded = neuralforecast_class.load(str(model_path))
        result["loaded"] = True
        result["failed_phase"] = "predict_after_load"

        reload_phase_baseline = cuda_phase_baseline() if require_gpu else {}
        result["cuda_reload_phase_baseline"] = reload_phase_baseline

        if policy == "stochastic":
            (
                after_samples,
                after_point,
                after_values,
                after_duplicate,
                after_keys_consistent,
            ) = collect_prediction_samples(
                loaded,
                alias=alias,
                verbose=verbose,
                random_seed=random_seed,
                sample_count=stochastic_samples,
            )
            first_after = after_samples[0].drop(columns=["sample_index", "seed"])
            first_after = first_after.rename(columns={"prediction": after_point})
            first_after.to_csv(model_path.parent / "prediction_after_load.csv", index=False)
            pd.concat(after_samples, ignore_index=True).to_csv(
                model_path.parent / "prediction_samples_after_load.csv",
                index=False,
            )
            after_reference = first_after
            result["duplicate_keys_after"] = after_duplicate
        else:
            seed_runtime(random_seed)
            prediction_after = loaded.predict(verbose=verbose)
            prediction_after.to_csv(model_path.parent / "prediction_after_load.csv", index=False)
            after_reference, after_point, after_vector, after_duplicate = prediction_frame(
                prediction_after,
                alias,
            )
            after_values = after_vector.reshape(1, -1)
            after_keys_consistent = True
            result["duplicate_keys_after"] = after_duplicate

        result["predicted"] = True
        result["point_column_after"] = after_point
        loaded_model = fitted_inner_model(loaded)
        result["state_after_finite"] = state_dict_finite(loaded_model)
        runtime_reload = torch_runtime_snapshot(loaded_model)
        gpu_reload = _safe_gpu_process_snapshot()
        reload_phase = cuda_phase_evidence(
            runtime_reload,
            gpu_reload,
            reload_phase_baseline if require_gpu else None,
        )
        reload_cuda = bool(reload_phase["verified"])
        result["runtime_reload_inference"] = runtime_reload
        result["gpu_reload_inference"] = gpu_reload
        result["cuda_reload_phase_evidence"] = reload_phase
        result["cuda_reload_inference_evidence"] = reload_cuda

        shape_match = before_values.shape == after_values.shape
        key_match = bool(
            before_keys_consistent
            and after_keys_consistent
            and key_frames_match(before_reference, after_reference)
        )
        prediction_match, maximum, comparison = compare_predictions(
            policy=policy,
            before_values=before_values,
            after_values=after_values,
            key_match=key_match,
            rtol=rtol,
            atol=atol,
            random_seed=random_seed,
        )
        finite_before = bool(np.isfinite(before_values).all())
        finite_after = bool(np.isfinite(after_values).all())
        formal_training = result["formal_cuda_training_evidence"]

        failed_checks: list[str] = []
        if not shape_match:
            failed_checks.append("prediction_shape_match")
        if not key_match:
            failed_checks.append("prediction_key_match")
        if not finite_before:
            failed_checks.append("finite_prediction_samples_before")
        if not finite_after:
            failed_checks.append("finite_predictions_after")
        if not prediction_match:
            failed_checks.append(
                "prediction_distribution_match"
                if policy == "stochastic"
                else "prediction_value_match"
            )
        if not result["state_after_finite"]:
            failed_checks.append("finite_state_dict_after")
        if result["duplicate_keys_before"]:
            failed_checks.append("unique_prediction_keys_before")
        if result["duplicate_keys_after"]:
            failed_checks.append("unique_prediction_keys_after")
        if require_gpu and not formal_training:
            failed_checks.append("gpu_training_evidence")
        if require_gpu and not pre_cuda:
            failed_checks.append("gpu_pre_save_inference_evidence")
        if require_gpu and not reload_cuda:
            failed_checks.append("gpu_reload_inference_evidence")

        result.update(
            {
                "status": "PASS" if not failed_checks else "FAIL",
                "failed_phase": None if not failed_checks else "verification",
                "shape_match": shape_match,
                "key_match": key_match,
                "finite": bool(finite_before and finite_after),
                "prediction_match": prediction_match,
                "max_abs_diff": maximum,
                "prediction_comparison": comparison,
                "cuda_execution_evidence": bool(
                    formal_training and pre_cuda and reload_cuda
                    if require_gpu
                    else pre_cuda or reload_cuda
                ),
                "cpu_fallback": bool(require_gpu and not reload_cuda),
                # Deprecated aliases retained for existing artifact consumers.
                "runtime_before": runtime_pre,
                "runtime_after": runtime_reload,
                "gpu_before": gpu_pre,
                "gpu_after": gpu_reload,
                "failed_checks": failed_checks,
            }
        )
        return _finish_result(model_path, result)
    except RuntimeCertificationFailure:
        raise
    except Exception as exc:
        if not result["failed_checks"]:
            result["failed_checks"] = [f"{result['failed_phase']}_exception"]
        result.update(
            {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )
        return _finish_result(model_path, result)

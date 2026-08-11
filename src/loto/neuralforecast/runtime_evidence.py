from __future__ import annotations

from typing import Any

import numpy as np

from loto.auto_campaign.runtime import (
    cuda_phase_baseline,
    gpu_process_snapshot,
    torch_runtime_snapshot,
)
from loto.neuralforecast.training_worker_evidence import TrainingWorkerEvidence


def fitted_inner_model(neuralforecast: Any) -> Any | None:
    models = getattr(neuralforecast, "models", None)
    if not models or len(models) != 1:
        return None
    return getattr(models[0], "model", models[0])


def state_dict_finite(model: Any | None) -> bool:
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


def safe_gpu_process_snapshot() -> dict[str, Any]:
    try:
        return gpu_process_snapshot()
    except FileNotFoundError:
        return {
            "pid": None,
            "returncode": 127,
            "gpu_pid_verified": False,
            "external_gpu_pid_verified": False,
            "verification_method": "none",
            "rows": [],
            "error": "nvidia-smi not found",
        }


def runtime_has_cuda(snapshot: dict[str, Any]) -> bool:
    return bool(
        str(snapshot.get("parameter_device", "")).startswith("cuda")
        or str(snapshot.get("trainer_root_device", "")).startswith("cuda")
        or snapshot.get("cuda_memory_allocated", 0) > 0
        or snapshot.get("cuda_memory_reserved", 0) > 0
        or snapshot.get("cuda_peak_memory_allocated", 0) > 0
    )


def cuda_phase_evidence(
    runtime: dict[str, Any],
    gpu_process: dict[str, Any],
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    """Verify CUDA execution for one measured phase without stale allocator state.

    External `nvidia-smi` PID evidence remains authoritative when available. The
    process-local fallback is accepted only when a peak-reset baseline was
    captured immediately before the operation and PyTorch's peak allocation
    rose above the bytes already allocated at that baseline.
    """

    external_verified = bool(gpu_process.get("external_gpu_pid_verified"))
    payload: dict[str, Any] = {
        "verified": external_verified,
        "verification_method": (
            "nvidia_smi_compute_apps" if external_verified else "none"
        ),
        "external_gpu_pid_verified": external_verified,
        "process_local_phase_verified": False,
        "same_pid": False,
        "peak_reset": False,
        "baseline_allocated_bytes": 0,
        "peak_after_bytes": int(runtime.get("cuda_peak_memory_allocated") or 0),
        "peak_delta_bytes": 0,
    }
    if external_verified or not baseline:
        return payload

    baseline_pid = baseline.get("pid")
    runtime_pid = runtime.get("pid")
    same_pid = bool(baseline_pid is not None and baseline_pid == runtime_pid)
    peak_reset = baseline.get("peak_reset") is True
    baseline_allocated = int(baseline.get("cuda_memory_allocated") or 0)
    peak_after = int(runtime.get("cuda_peak_memory_allocated") or 0)
    peak_delta = max(0, peak_after - baseline_allocated)
    same_device = baseline.get("cuda_current_device") == runtime.get("cuda_current_device")
    local_verified = bool(
        same_pid
        and same_device
        and peak_reset
        and baseline.get("cuda_available") is True
        and runtime.get("cuda_available") is True
        and peak_delta > 0
    )
    payload.update(
        {
            "verified": local_verified,
            "verification_method": (
                "torch_process_local_peak_delta" if local_verified else "none"
            ),
            "process_local_phase_verified": local_verified,
            "same_pid": same_pid,
            "same_device": same_device,
            "peak_reset": peak_reset,
            "baseline_allocated_bytes": baseline_allocated,
            "peak_after_bytes": peak_after,
            "peak_delta_bytes": peak_delta,
        }
    )
    return payload


def phase_has_cuda(
    runtime: dict[str, Any],
    gpu_process: dict[str, Any],
    *,
    baseline: dict[str, Any] | None = None,
) -> bool:
    return bool(cuda_phase_evidence(runtime, gpu_process, baseline).get("verified"))


def extract_training_evidence(neuralforecast: Any) -> dict[str, Any] | None:
    models = getattr(neuralforecast, "models", None) or []
    for wrapper in models:
        for candidate in (wrapper, getattr(wrapper, "model", None)):
            if candidate is None:
                continue
            for attribute in (
                "training_runtime_evidence",
                "runtime_training_evidence",
                "trial_runtime_evidence",
            ):
                value = getattr(candidate, attribute, None)
                if isinstance(value, dict):
                    return dict(value)
    return None


def formal_training_cuda(training_evidence: dict[str, Any] | None) -> bool:
    """Accept only the versioned in-training callback contract, never driver guesses."""

    if not training_evidence:
        return False
    try:
        evidence = TrainingWorkerEvidence.model_validate(training_evidence)
    except Exception:
        return False
    return bool(
        evidence.status == "PASS"
        and evidence.require_gpu
        and evidence.formal_training_proof
        and evidence.cuda_execution_evidence
        and evidence.observed_fit_start
        and evidence.observed_train_start
        and evidence.observed_train_batch
        and evidence.observed_train_end
        and evidence.device_cuda
        and evidence.vram_positive
        and evidence.gpu_pid_verified
        and evidence.runtime_pid_match
        and evidence.gpu_pid_match
        and evidence.worker_pid > 0
        and evidence.runtime.get("pid") == evidence.worker_pid
        and evidence.gpu_process.get("pid") == evidence.worker_pid
        and not evidence.cpu_fallback
        and not evidence.failed_checks
    )


__all__ = [
    "cuda_phase_baseline",
    "cuda_phase_evidence",
    "extract_training_evidence",
    "fitted_inner_model",
    "formal_training_cuda",
    "phase_has_cuda",
    "safe_gpu_process_snapshot",
    "state_dict_finite",
    "torch_runtime_snapshot",
]

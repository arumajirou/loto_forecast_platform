from __future__ import annotations

from typing import Any

import numpy as np

from loto.auto_campaign.runtime import gpu_process_snapshot, torch_runtime_snapshot


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


def phase_has_cuda(runtime: dict[str, Any], gpu_process: dict[str, Any]) -> bool:
    return bool(runtime_has_cuda(runtime) or gpu_process.get("gpu_pid_verified"))


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
    if not training_evidence:
        return False
    return bool(
        training_evidence.get("formal_training_proof") is True
        and training_evidence.get("cuda_execution_evidence") is True
    )


__all__ = [
    "extract_training_evidence",
    "fitted_inner_model",
    "formal_training_cuda",
    "phase_has_cuda",
    "safe_gpu_process_snapshot",
    "state_dict_finite",
    "torch_runtime_snapshot",
]

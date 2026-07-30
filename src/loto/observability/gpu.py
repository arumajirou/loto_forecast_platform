from __future__ import annotations

import os
import subprocess
from typing import Any


def collect_gpu_evidence(*, gpu_required: bool, model: Any | None = None, batch: Any | None = None) -> dict:
    evidence: dict[str, Any] = {
        "gpu_required": gpu_required,
        "pid": os.getpid(),
        "model_device": "unknown",
        "batch_device": "unknown",
        "vram_peak_bytes": 0,
    }
    # CPU-authorized trials do not need to initialize CUDA or call nvidia-smi.
    # This avoids driver initialization hangs in containers without GPU access.
    if not gpu_required and model is None and batch is None:
        evidence.update({"model_device": "cpu", "batch_device": "cpu"})
        evidence.update(evaluate_gpu_evidence(evidence))
        return evidence
    try:
        import torch
        evidence.update({
            "torch_version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": torch.version.cuda,
            "gpu_count": torch.cuda.device_count(),
        })
        if model is not None:
            try:
                evidence["model_device"] = str(next(model.parameters()).device)
            except (StopIteration, AttributeError):
                pass
        if batch is not None:
            evidence["batch_device"] = str(getattr(batch, "device", "unknown"))
        if torch.cuda.is_available():
            evidence["vram_allocated_bytes"] = int(torch.cuda.memory_allocated())
            evidence["vram_peak_bytes"] = int(torch.cuda.max_memory_allocated())
            evidence["gpu_name"] = torch.cuda.get_device_name(0)
    except Exception as exc:  # noqa: BLE001
        evidence["torch_error"] = str(exc)
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,gpu_uuid,used_memory", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        evidence["nvidia_smi_processes"] = proc.stdout.strip().splitlines() if proc.returncode == 0 else []
    except Exception as exc:  # noqa: BLE001
        evidence["nvidia_smi_error"] = str(exc)
    evidence.update(evaluate_gpu_evidence(evidence))
    return evidence


def evaluate_gpu_evidence(evidence: dict) -> dict:
    if not evidence.get("gpu_required", False):
        return {"eligible": True, "reasons": ["cpu_execution_authorized"]}
    reasons: list[str] = []
    model_cuda = str(evidence.get("model_device", "")).startswith("cuda")
    batch_cuda = str(evidence.get("batch_device", "")).startswith("cuda")
    vram = int(evidence.get("vram_peak_bytes", 0) or 0)
    if not model_cuda:
        reasons.append("model_not_on_cuda")
    if not batch_cuda:
        reasons.append("batch_not_on_cuda")
    if vram <= 0:
        reasons.append("no_vram_peak_evidence")
    return {"eligible": not reasons, "reasons": reasons or ["gpu_evidence_complete"]}

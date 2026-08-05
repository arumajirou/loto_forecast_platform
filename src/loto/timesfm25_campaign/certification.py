from __future__ import annotations

from dataclasses import dataclass

from loto.adapters.timesfm25.contracts import GPUExecutionEvidence, RuntimeEvidence


@dataclass(frozen=True)
class CertificationVerdict:
    status: str
    reasons: tuple[str, ...]


def judge_gpu_certification(
    runtime: RuntimeEvidence,
    gpu: GPUExecutionEvidence,
) -> CertificationVerdict:
    reasons: list[str] = []
    if not gpu.requested:
        return CertificationVerdict("NOT_REQUESTED", ())
    if runtime.cpu_fallback or gpu.cpu_fallback:
        reasons.append("CPU_FALLBACK")
    if not gpu.gpu_used:
        reasons.append("GPU_NOT_OBSERVED")
    if not gpu.external_pid_match:
        reasons.append("EXTERNAL_PID_NOT_MATCHED")
    if gpu.vram_peak_bytes <= 0:
        reasons.append("VRAM_PEAK_NOT_OBSERVED")
    if not runtime.model_parameter_device.startswith("cuda"):
        reasons.append("MODEL_PARAMETER_NOT_CUDA")
    if not runtime.mean_output_device.startswith("cuda"):
        reasons.append("MEAN_OUTPUT_NOT_CUDA")
    if not runtime.quantile_output_device.startswith("cuda"):
        reasons.append("QUANTILE_OUTPUT_NOT_CUDA")
    return CertificationVerdict("PASS" if not reasons else "FAIL", tuple(reasons))

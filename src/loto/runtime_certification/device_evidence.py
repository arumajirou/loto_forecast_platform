"""Device and external GPU evidence validation helpers."""

from __future__ import annotations

from .contracts import DeviceEvidence
from .statuses import CertificationProfile, EvidenceOrigin


class DeviceEvidenceError(RuntimeError):
    pass


def validate_device_evidence(
    evidence: DeviceEvidence,
    *,
    profile: CertificationProfile,
) -> DeviceEvidence:
    if profile == CertificationProfile.CPU_SMOKE and evidence.requested_device != "cpu":
        raise DeviceEvidenceError("CPU_SMOKE requires a CPU request")
    if profile == CertificationProfile.GPU_FORMAL and evidence.requested_device != "cuda":
        raise DeviceEvidenceError("GPU_FORMAL requires a CUDA request")
    return evidence


def formal_gpu_evidence_available(evidence: DeviceEvidence) -> bool:
    return (
        evidence.requested_device == "cuda"
        and evidence.origin == EvidenceOrigin.REAL
        and evidence.provider_gpu_pid == evidence.provider_pid
        and evidence.gpu_uuid is not None
        and evidence.peak_vram_bytes > 0
        and evidence.pid_released_after_exit
        and bool(evidence.external_gpu_samples)
    )

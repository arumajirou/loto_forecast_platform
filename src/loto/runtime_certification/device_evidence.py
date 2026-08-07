"""Device and external GPU evidence validation helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .contracts import DeviceEvidence
from .statuses import CertificationProfile, EvidenceOrigin


class DeviceEvidenceError(RuntimeError):
    pass


def read_process_identity_sha256(pid: int) -> str | None:
    """Bind a Linux PID to its boot and process-start identity without extra dependencies."""
    if pid < 1:
        return None
    try:
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        stat_row = Path(f"/proc/{pid}/stat").read_text(encoding="ascii").strip()
        command_end = stat_row.rfind(")")
        if command_end < 0:
            return None
        fields_after_command = stat_row[command_end + 2 :].split()
        start_time_ticks = fields_after_command[19]
    except (IndexError, OSError, UnicodeError, ValueError):
        return None
    payload = f"{boot_id}:{pid}:{start_time_ticks}".encode("ascii")
    return hashlib.sha256(payload).hexdigest()


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
        and evidence.provider_process_identity_sha256 is not None
        and evidence.gpu_uuid is not None
        and evidence.peak_vram_bytes > 0
        and evidence.pid_released_after_exit
        and any(
            sample.provider_pid == evidence.provider_pid
            and sample.gpu_uuid == evidence.gpu_uuid
            and sample.provider_process_identity_sha256
            == evidence.provider_process_identity_sha256
            for sample in evidence.external_gpu_samples
        )
    )

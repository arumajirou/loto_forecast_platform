from __future__ import annotations

import math
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from .manifests import CheckpointLane, require_executable_lane
from .runtime_models import GPUProcessSample, RuntimeCertificationError, utc_now


def parse_nvidia_compute_apps(
    output: str, *, observed_at_utc: str | None = None
) -> list[GPUProcessSample]:
    timestamp = observed_at_utc or utc_now()
    samples: list[GPUProcessSample] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("No running processes found"):
            continue
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 3:
            raise RuntimeCertificationError(f"unexpected nvidia-smi compute-app row: {line}")
        pid_text, gpu_uuid, memory_mib_text = fields
        try:
            pid = int(pid_text)
            memory_mib = int(memory_mib_text)
        except ValueError as exc:
            raise RuntimeCertificationError(f"invalid nvidia-smi compute-app row: {line}") from exc
        samples.append(
            GPUProcessSample(
                pid=pid,
                gpu_uuid=gpu_uuid,
                used_memory_bytes=memory_mib * 1024 * 1024,
                observed_at_utc=timestamp,
            )
        )
    return samples


def query_nvidia_compute_apps(command: str = "nvidia-smi") -> list[GPUProcessSample]:
    completed = subprocess.run(
        [
            command,
            "--query-compute-apps=pid,gpu_uuid,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeCertificationError(
            "nvidia-smi compute-app query failed: "
            f"exit={completed.returncode}, stderr={completed.stderr.strip()}"
        )
    return parse_nvidia_compute_apps(completed.stdout)


def parameter_devices(response: Mapping[str, Any]) -> list[str]:
    gpu_evidence = response.get("gpu_evidence")
    if not isinstance(gpu_evidence, Mapping):
        return []
    values = gpu_evidence.get("model_parameter_devices", [])
    if not isinstance(values, list):
        return []
    return [str(value) for value in values]


def validate_provider_response(
    response: Mapping[str, Any],
    *,
    expected_device: Literal["cpu", "cuda"],
    process_pid: int,
    external_samples: Sequence[GPUProcessSample],
    expected_seed: int,
) -> tuple[list[float], dict[str, Any]]:
    if response.get("status") != "OK":
        raise RuntimeCertificationError(
            f"provider status is not OK: {response.get('status')} {response.get('message', '')}"
        )
    if response.get("schema_version") != 1:
        raise RuntimeCertificationError("provider schema_version must be 1")
    predictions_raw = response.get("predictions")
    if not isinstance(predictions_raw, list) or len(predictions_raw) != 37:
        raise RuntimeCertificationError("provider prediction shape must be [37]")
    predictions = [float(value) for value in predictions_raw]
    if not all(math.isfinite(value) for value in predictions):
        raise RuntimeCertificationError("provider predictions contain non-finite values")
    if response.get("prediction_shape") != [37] or response.get("finite") is not True:
        raise RuntimeCertificationError("provider shape/finite declarations do not match output")

    properties = response.get("properties")
    if not isinstance(properties, Mapping):
        raise RuntimeCertificationError("provider properties are missing")
    manifest = require_executable_lane(CheckpointLane.V2_REG_LEGACY)
    if properties.get("weight_sha256") != manifest.sha256:
        raise RuntimeCertificationError("provider weight SHA-256 differs from reviewed manifest")
    if int(properties.get("seed", -1)) != expected_seed:
        raise RuntimeCertificationError(
            "provider effective seed differs from certification request"
        )

    gpu = response.get("gpu_evidence")
    if not isinstance(gpu, Mapping):
        raise RuntimeCertificationError("provider gpu_evidence is missing")
    requested = str(gpu.get("requested_device"))
    execution = str(gpu.get("execution_device"))
    cpu_fallback = bool(gpu.get("cpu_fallback"))
    if requested != expected_device or execution != expected_device or cpu_fallback:
        raise RuntimeCertificationError(
            "device identity mismatch or CPU fallback: "
            f"requested={requested}, execution={execution}, fallback={cpu_fallback}"
        )

    devices = parameter_devices(response)
    if expected_device == "cuda":
        provider_pid = gpu.get("gpu_pid")
        if provider_pid != process_pid:
            raise RuntimeCertificationError(
                f"provider GPU PID mismatch: expected={process_pid}, actual={provider_pid}"
            )
        if int(gpu.get("peak_vram_bytes", 0)) <= 0:
            raise RuntimeCertificationError("provider did not report positive peak VRAM")
        if not any(device.startswith("cuda") for device in devices):
            raise RuntimeCertificationError("provider did not expose CUDA model parameter evidence")
        matching_samples = [sample for sample in external_samples if sample.pid == process_pid]
        if not matching_samples:
            raise RuntimeCertificationError(
                "external nvidia-smi evidence did not observe provider PID"
            )
        if max(sample.used_memory_bytes for sample in matching_samples) <= 0:
            raise RuntimeCertificationError("external GPU sample did not report positive VRAM")
    elif gpu.get("gpu_pid") is not None:
        raise RuntimeCertificationError("CPU smoke must not report a GPU PID")

    return predictions, dict(gpu)

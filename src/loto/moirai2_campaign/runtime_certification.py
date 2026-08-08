from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


class RuntimeCertificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ComputeProcessRecord:
    pid: int
    gpu_uuid: str
    used_memory_mib: int


@dataclass(frozen=True)
class GpuMemoryRecord:
    gpu_uuid: str
    used_memory_mib: int


@dataclass(frozen=True)
class PredictionComparison:
    process_a: int
    process_b: int
    distinct_processes: bool
    prediction_sha256_a: str
    prediction_sha256_b: str
    exact_prediction_match: bool
    maximum_absolute_difference: float
    artifact_identity_match: bool
    model_identity_match: bool
    covariate_identity_match: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExternalGpuCertification:
    requested_device: str
    provider_pid: int
    gpu_uuid: str | None
    external_pid_match: bool
    peak_process_memory_mib: int
    pid_absent_after_exit: bool
    vram_before_mib: int | None
    vram_after_mib: int | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_compute_process_csv(text: str) -> list[ComputeProcessRecord]:
    records: list[ComputeProcessRecord] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith("no running processes"):
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3:
            raise RuntimeCertificationError(f"invalid compute-process row: {raw_line!r}")
        pid_text, gpu_uuid, memory_text = parts
        try:
            records.append(
                ComputeProcessRecord(
                    pid=int(pid_text),
                    gpu_uuid=gpu_uuid,
                    used_memory_mib=int(memory_text),
                )
            )
        except ValueError as exc:
            raise RuntimeCertificationError(
                f"invalid compute-process values: {raw_line!r}"
            ) from exc
    return records


def parse_gpu_memory_csv(text: str) -> list[GpuMemoryRecord]:
    records: list[GpuMemoryRecord] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 2:
            raise RuntimeCertificationError(f"invalid GPU-memory row: {raw_line!r}")
        gpu_uuid, memory_text = parts
        try:
            records.append(
                GpuMemoryRecord(
                    gpu_uuid=gpu_uuid,
                    used_memory_mib=int(memory_text),
                )
            )
        except ValueError as exc:
            raise RuntimeCertificationError(f"invalid GPU-memory values: {raw_line!r}") from exc
    return records


def _runtime(response: dict[str, Any]) -> dict[str, Any]:
    value = response.get("runtime_evidence")
    if not isinstance(value, dict):
        raise RuntimeCertificationError("runtime_evidence is required")
    return value


def _gpu(response: dict[str, Any]) -> dict[str, Any]:
    value = response.get("gpu_evidence")
    if not isinstance(value, dict):
        raise RuntimeCertificationError("gpu_evidence is required")
    return value


def _prediction_identity(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "point_forecast": response.get("point_forecast"),
        "quantiles": response.get("quantiles"),
        "series_identity": response.get("series_identity"),
        "prediction_index": response.get("prediction_index"),
    }


def _artifact_identity(response: dict[str, Any]) -> dict[str, Any]:
    artifact = response.get("artifact_reference")
    if not isinstance(artifact, dict):
        raise RuntimeCertificationError("artifact_reference is required")
    required = {"model_revision", "config_sha256", "weight_sha256"}
    missing = sorted(required - set(artifact))
    if missing:
        raise RuntimeCertificationError(f"artifact identity keys are missing: {missing}")
    return {key: artifact[key] for key in sorted(required)}


def _covariate_identity(response: dict[str, Any]) -> dict[str, Any]:
    evidence = response.get("covariate_evidence")
    if not isinstance(evidence, dict):
        raise RuntimeCertificationError("covariate_evidence is required")
    return evidence


def _flatten_numbers(value: Any) -> Iterable[float]:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield float(value)
        return
    if isinstance(value, dict):
        for key in sorted(value):
            yield from _flatten_numbers(value[key])
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _flatten_numbers(item)


def maximum_absolute_difference(first: Any, second: Any) -> float:
    first_values = list(_flatten_numbers(first))
    second_values = list(_flatten_numbers(second))
    if len(first_values) != len(second_values):
        return math.inf
    if not first_values:
        return 0.0
    return max(abs(left - right) for left, right in zip(first_values, second_values, strict=True))


def validate_provider_device_evidence(response: dict[str, Any]) -> None:
    if response.get("status") != "OK":
        raise RuntimeCertificationError("provider response is not OK")
    runtime = _runtime(response)
    gpu = _gpu(response)
    requested = str(runtime.get("requested_device"))
    execution = str(runtime.get("execution_device"))
    if requested not in {"cpu", "cuda"} or execution != requested:
        raise RuntimeCertificationError("requested and execution devices must match")
    if bool(runtime.get("cpu_fallback")) or bool(gpu.get("cpu_fallback")):
        raise RuntimeCertificationError("CPU fallback is forbidden")
    provider_pid = int(runtime.get("process_id", -1))
    if provider_pid < 1 or int(gpu.get("provider_pid", -2)) != provider_pid:
        raise RuntimeCertificationError("provider PID evidence is inconsistent")
    model_device = str(runtime.get("model_parameter_device", ""))
    effective = response.get("effective_arguments")
    if not isinstance(effective, dict):
        raise RuntimeCertificationError("effective_arguments is required")
    predictor_device = str(effective.get("predictor_device", ""))
    forward = effective.get("forward_device_evidence")
    if not isinstance(forward, dict):
        raise RuntimeCertificationError("forward device evidence is required")
    input_devices = [str(item) for item in forward.get("input_tensor_devices", [])]
    output_devices = [str(item) for item in forward.get("output_tensor_devices", [])]
    if int(forward.get("forward_call_count", 0)) < 1:
        raise RuntimeCertificationError("no model forward call was observed")
    if not input_devices or not output_devices:
        raise RuntimeCertificationError("input and output tensor devices are required")
    expected_prefix = requested
    observed = [model_device, predictor_device, *input_devices, *output_devices]
    if any(not value.startswith(expected_prefix) for value in observed):
        raise RuntimeCertificationError(
            f"provider device evidence does not stay on {requested}: {observed}"
        )
    if requested == "cuda":
        if int(gpu.get("gpu_pid", -1)) != provider_pid:
            raise RuntimeCertificationError("provider GPU PID does not match the process PID")
        if int(gpu.get("peak_vram_bytes", 0)) <= 0:
            raise RuntimeCertificationError("CUDA execution requires positive peak VRAM")
    elif gpu.get("gpu_pid") is not None:
        raise RuntimeCertificationError("CPU execution must not report a GPU PID")


def compare_provider_responses(
    first: dict[str, Any],
    second: dict[str, Any],
) -> PredictionComparison:
    validate_provider_device_evidence(first)
    validate_provider_device_evidence(second)
    first_runtime = _runtime(first)
    second_runtime = _runtime(second)
    process_a = int(first_runtime["process_id"])
    process_b = int(second_runtime["process_id"])
    if process_a == process_b:
        raise RuntimeCertificationError("reload certification requires distinct process IDs")
    if first_runtime.get("runtime_lane") != second_runtime.get("runtime_lane"):
        raise RuntimeCertificationError("runtime lanes differ between reload runs")
    first_prediction = _prediction_identity(first)
    second_prediction = _prediction_identity(second)
    hash_a = sha256_payload(first_prediction)
    hash_b = sha256_payload(second_prediction)
    comparison = PredictionComparison(
        process_a=process_a,
        process_b=process_b,
        distinct_processes=True,
        prediction_sha256_a=hash_a,
        prediction_sha256_b=hash_b,
        exact_prediction_match=hash_a == hash_b,
        maximum_absolute_difference=maximum_absolute_difference(
            first_prediction,
            second_prediction,
        ),
        artifact_identity_match=_artifact_identity(first) == _artifact_identity(second),
        model_identity_match=first.get("model_identity") == second.get("model_identity"),
        covariate_identity_match=(_covariate_identity(first) == _covariate_identity(second)),
    )
    if not comparison.exact_prediction_match:
        raise RuntimeCertificationError("separate-process prediction SHA-256 values do not match")
    if not comparison.artifact_identity_match:
        raise RuntimeCertificationError("snapshot artifact identity changed between runs")
    if not comparison.model_identity_match:
        raise RuntimeCertificationError("model identity changed between runs")
    if not comparison.covariate_identity_match:
        raise RuntimeCertificationError("covariate evidence changed between runs")
    return comparison


def certify_external_gpu_evidence(
    *,
    response: dict[str, Any],
    samples: list[ComputeProcessRecord],
    before_memory: list[GpuMemoryRecord],
    after_memory: list[GpuMemoryRecord],
    after_processes: list[ComputeProcessRecord],
) -> ExternalGpuCertification:
    validate_provider_device_evidence(response)
    runtime = _runtime(response)
    gpu = _gpu(response)
    requested = str(runtime["requested_device"])
    provider_pid = int(runtime["process_id"])
    if requested == "cpu":
        if any(record.pid == provider_pid for record in samples):
            raise RuntimeCertificationError("CPU run appeared in external GPU process samples")
        return ExternalGpuCertification(
            requested_device="cpu",
            provider_pid=provider_pid,
            gpu_uuid=None,
            external_pid_match=False,
            peak_process_memory_mib=0,
            pid_absent_after_exit=all(record.pid != provider_pid for record in after_processes),
            vram_before_mib=None,
            vram_after_mib=None,
        )
    matching = [record for record in samples if record.pid == provider_pid]
    if not matching:
        raise RuntimeCertificationError("external nvidia-smi never observed the provider PID")
    uuids = {record.gpu_uuid for record in matching}
    if len(uuids) != 1:
        raise RuntimeCertificationError("provider PID appeared on multiple GPU UUIDs")
    gpu_uuid = next(iter(uuids))
    if any(record.pid == provider_pid for record in after_processes):
        raise RuntimeCertificationError("provider PID remains in nvidia-smi after process exit")
    before_map = {record.gpu_uuid: record.used_memory_mib for record in before_memory}
    after_map = {record.gpu_uuid: record.used_memory_mib for record in after_memory}
    if gpu.get("gpu_pid") != provider_pid:
        raise RuntimeCertificationError("provider and external GPU PID evidence disagree")
    return ExternalGpuCertification(
        requested_device="cuda",
        provider_pid=provider_pid,
        gpu_uuid=gpu_uuid,
        external_pid_match=True,
        peak_process_memory_mib=max(record.used_memory_mib for record in matching),
        pid_absent_after_exit=True,
        vram_before_mib=before_map.get(gpu_uuid),
        vram_after_mib=after_map.get(gpu_uuid),
    )


def write_sha256_manifest(root: Path, output_path: Path) -> None:
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.resolve() != output_path.resolve()
    )
    lines = [f"{sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in paths]
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

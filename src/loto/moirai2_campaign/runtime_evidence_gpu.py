from __future__ import annotations

from pathlib import Path
from typing import Any

from loto.moirai2_campaign.runtime_evidence_common import (
    RuntimeEvidenceGateError,
    _required_file,
    canonical_json_bytes,
    load_json_object,
    sha256_file,
)
from loto.moirai2_campaign.runtime_evidence_prediction import (
    _require_equal,
    _require_true,
)

def _snapshot_records(snapshot: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(snapshot, dict):
        raise RuntimeEvidenceGateError("GPU monitor snapshot is not an object")
    records = snapshot.get(key)
    if not isinstance(records, list) or not all(
        isinstance(item, dict) for item in records
    ):
        raise RuntimeEvidenceGateError(f"GPU monitor {key} records are invalid")
    return records


def _memory_map(snapshot: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for record in _snapshot_records(snapshot, "memory"):
        gpu_uuid = str(record.get("gpu_uuid", ""))
        memory = int(record.get("used_memory_mib", -1))
        if not gpu_uuid or memory < 0 or gpu_uuid in result:
            raise RuntimeEvidenceGateError("GPU monitor memory record is invalid")
        result[gpu_uuid] = memory
    return result


def _process_records(snapshot: dict[str, Any]) -> list[tuple[int, str, int]]:
    result: list[tuple[int, str, int]] = []
    for record in _snapshot_records(snapshot, "processes"):
        pid = int(record.get("pid", -1))
        gpu_uuid = str(record.get("gpu_uuid", ""))
        memory = int(record.get("used_memory_mib", -1))
        if pid < 1 or not gpu_uuid or memory < 0:
            raise RuntimeEvidenceGateError("GPU monitor process record is invalid")
        result.append((pid, gpu_uuid, memory))
    return result


def _monitor_errors(snapshot: dict[str, Any]) -> list[str]:
    errors = snapshot.get("errors", [])
    if not isinstance(errors, list) or not all(isinstance(item, str) for item in errors):
        raise RuntimeEvidenceGateError("GPU monitor errors are invalid")
    return errors


def _verify_gpu_monitor(
    *,
    monitor: dict[str, Any],
    provider_pid: int,
    requested_device: str,
) -> dict[str, Any]:
    before = monitor.get("before")
    samples = monitor.get("samples")
    after = monitor.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise RuntimeEvidenceGateError("GPU monitor before/after snapshots are missing")
    if not isinstance(samples, list) or not all(isinstance(item, dict) for item in samples):
        raise RuntimeEvidenceGateError("GPU monitor samples are invalid")
    before_memory = _memory_map(before)
    after_memory = _memory_map(after)
    sample_processes = [
        record
        for sample in samples
        for record in _process_records(sample)
    ]
    after_processes = _process_records(after)
    if any(pid == provider_pid for pid, _, _ in after_processes):
        raise RuntimeEvidenceGateError("provider PID remains in GPU monitor after exit")
    matching = [record for record in sample_processes if record[0] == provider_pid]
    if requested_device == "cpu":
        if matching:
            raise RuntimeEvidenceGateError("CPU provider appeared in GPU monitor samples")
        return {
            "requested_device": "cpu",
            "provider_pid": provider_pid,
            "gpu_uuid": None,
            "external_pid_match": False,
            "peak_process_memory_mib": 0,
            "pid_absent_after_exit": True,
            "vram_before_mib": None,
            "vram_after_mib": None,
        }
    all_snapshots = [before, *samples, after]
    errors = [error for snapshot in all_snapshots for error in _monitor_errors(snapshot)]
    if errors:
        raise RuntimeEvidenceGateError(f"CUDA GPU monitor contains errors: {errors}")
    if not matching:
        raise RuntimeEvidenceGateError("CUDA provider PID is absent from GPU monitor samples")
    uuids = {gpu_uuid for _, gpu_uuid, _ in matching}
    if len(uuids) != 1:
        raise RuntimeEvidenceGateError("CUDA provider appears on multiple GPU UUIDs")
    gpu_uuid = next(iter(uuids))
    return {
        "requested_device": "cuda",
        "provider_pid": provider_pid,
        "gpu_uuid": gpu_uuid,
        "external_pid_match": True,
        "peak_process_memory_mib": max(memory for _, _, memory in matching),
        "pid_absent_after_exit": True,
        "vram_before_mib": before_memory.get(gpu_uuid),
        "vram_after_mib": after_memory.get(gpu_uuid),
    }

def _verify_run_evidence(
    *,
    run_dir: Path,
    response: dict[str, Any],
    process_id: int,
    requested_device: str,
) -> dict[str, Any]:
    evidence = load_json_object(_required_file(run_dir, "run_evidence.json"))
    _require_equal(evidence.get("process_id"), process_id, "run evidence PID differs")
    for key, relative in (
        ("request_sha256", "request.json"),
        ("response_sha256", "response.json"),
        ("stdout_sha256", "stdout.log"),
        ("stderr_sha256", "stderr.log"),
    ):
        actual = sha256_file(_required_file(run_dir, relative))
        _require_equal(evidence.get(key), actual, f"{key} differs")
    exit_code = _required_file(run_dir, "exit_code.txt").read_text(
        encoding="utf-8"
    ).strip()
    _require_equal(exit_code, "0", "provider exit code differs")
    external = evidence.get("external_gpu")
    if not isinstance(external, dict):
        raise RuntimeEvidenceGateError("external GPU evidence is missing")
    monitor = load_json_object(_required_file(run_dir, "gpu_monitor.json"))
    derived_external = _verify_gpu_monitor(
        monitor=monitor,
        provider_pid=process_id,
        requested_device=requested_device,
    )
    _require_equal(
        external,
        derived_external,
        "external GPU summary differs from monitor samples",
    )
    _require_equal(
        external.get("requested_device"),
        requested_device,
        "external requested device differs",
    )
    _require_equal(
        int(external.get("provider_pid", -1)),
        process_id,
        "external provider PID differs",
    )
    _require_true(
        external.get("pid_absent_after_exit"),
        "provider PID was not absent after exit",
    )
    if requested_device == "cuda":
        _require_true(
            external.get("external_pid_match"),
            "external CUDA provider PID was not observed",
        )
        if not str(external.get("gpu_uuid", "")):
            raise RuntimeEvidenceGateError("external GPU UUID is missing")
        if int(external.get("peak_process_memory_mib", 0)) <= 0:
            raise RuntimeEvidenceGateError(
                "external CUDA process memory is not positive"
            )
    else:
        _require_equal(
            external.get("gpu_uuid"),
            None,
            "CPU run reports an external GPU UUID",
        )
        _require_equal(
            int(external.get("peak_process_memory_mib", -1)),
            0,
            "CPU run reports external GPU memory",
        )
    stored_response = load_json_object(_required_file(run_dir, "response.json"))
    if canonical_json_bytes(stored_response) != canonical_json_bytes(response):
        raise RuntimeEvidenceGateError("run response differs from loaded response")
    embedded_response = evidence.get("response")
    if not isinstance(embedded_response, dict) or canonical_json_bytes(
        embedded_response
    ) != canonical_json_bytes(response):
        raise RuntimeEvidenceGateError("run evidence embedded response differs")
    return evidence



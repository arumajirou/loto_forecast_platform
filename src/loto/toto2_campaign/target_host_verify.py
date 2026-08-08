from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

_CASE_ID = re.compile(
    r"^(numbers3|numbers4|miniloto|loto6|loto7)-"
    r"c(128|256|512)-h(1|2|5)-(cpu|cuda)$"
)


@dataclass(frozen=True)
class VerifiedCase:
    case_id: str
    device: str
    response_status: str
    replay_exact: bool
    gpu_processes_verified: int


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json_bytes(data: bytes, name: str) -> dict[str, Any]:
    payload = json.loads(data.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {name}")
    return payload


def _safe_members(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    members: dict[str, zipfile.ZipInfo] = {}
    for info in archive.infolist():
        name = info.filename
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or not name:
            raise ValueError(f"unsafe archive member: {name!r}")
        if name in members:
            raise ValueError(f"duplicate archive member: {name}")
        if info.is_dir():
            continue
        if info.date_time != (1980, 1, 1, 0, 0, 0):
            raise ValueError(f"archive member has non-deterministic timestamp: {name}")
        members[name] = info
    return members


def _read_json(
    archive: zipfile.ZipFile,
    members: dict[str, zipfile.ZipInfo],
    name: str,
) -> dict[str, Any]:
    if name not in members:
        raise ValueError(f"archive is missing required file: {name}")
    return _load_json_bytes(archive.read(name), name)


def _verify_embedded_manifest(
    archive: zipfile.ZipFile,
    members: dict[str, zipfile.ZipInfo],
) -> None:
    manifest = _read_json(archive, members, "ARTIFACT_MANIFEST.json")
    entries = manifest.get("files")
    if not isinstance(entries, list) or manifest.get("file_count") != len(entries):
        raise ValueError("embedded artifact manifest file_count mismatch")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("embedded artifact entry must be an object")
        name = entry.get("path")
        if not isinstance(name, str) or name in seen:
            raise ValueError(f"invalid or duplicate manifest path: {name!r}")
        seen.add(name)
        if name not in members:
            raise ValueError(f"manifest file is missing from archive: {name}")
        data = archive.read(name)
        if len(data) != entry.get("size_bytes"):
            raise ValueError(f"manifest size mismatch: {name}")
        if _sha256_bytes(data) != entry.get("sha256"):
            raise ValueError(f"manifest hash mismatch: {name}")


def _verify_sha256s(
    archive: zipfile.ZipFile,
    members: dict[str, zipfile.ZipInfo],
) -> None:
    if "SHA256SUMS" not in members:
        raise ValueError("archive is missing required file: SHA256SUMS")
    manifest = _read_json(archive, members, "ARTIFACT_MANIFEST.json")
    expected = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
    observed: dict[str, str] = {}
    text = archive.read("SHA256SUMS").decode("utf-8")
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"invalid SHA256SUMS line: {line!r}")
        digest, name = parts[0], parts[1].lstrip(" *")
        if name in observed:
            raise ValueError(f"duplicate SHA256SUMS path: {name}")
        observed[name] = digest
    if observed != expected:
        raise ValueError("SHA256SUMS does not exactly match the artifact manifest")


def _verify_process_evidence(
    archive: zipfile.ZipFile,
    members: dict[str, zipfile.ZipInfo],
    case_id: str,
    process_name: str,
    device: str,
) -> int:
    prefix = f"cases/{case_id}/runtime/{process_name}"
    evidence = _read_json(
        archive,
        members,
        f"{prefix}/runtime_evidence.json",
    )
    if evidence.get("requested_device") != device:
        raise ValueError(f"requested device mismatch: {case_id}/{process_name}")
    if evidence.get("runtime_scope") != "FULL_INFERENCE":
        raise ValueError(f"runtime scope mismatch: {case_id}/{process_name}")
    if evidence.get("cpu_fallback") is not False:
        raise ValueError(f"CPU fallback detected: {case_id}/{process_name}")
    execution_device = str(evidence.get("execution_device", ""))
    model_device = str(evidence.get("model_device", ""))
    output_device = str(evidence.get("output_device", ""))
    if device == "cuda":
        for value, field in (
            (execution_device, "execution_device"),
            (model_device, "model_device"),
            (output_device, "output_device"),
        ):
            if not value.startswith("cuda"):
                raise ValueError(f"{field} is not CUDA: {case_id}/{process_name}")
        if evidence.get("external_gpu_pid_captured") is not True:
            raise ValueError(f"GPU PID was not captured: {case_id}/{process_name}")
        if not isinstance(evidence.get("peak_vram_bytes"), int):
            raise ValueError(f"peak VRAM is missing: {case_id}/{process_name}")
        if int(evidence["peak_vram_bytes"]) <= 0:
            raise ValueError(f"peak VRAM is not positive: {case_id}/{process_name}")
        gpu = _read_json(
            archive,
            members,
            f"{prefix}/external_gpu_pid_evidence.json",
        )
        if gpu.get("captured") is not True:
            raise ValueError(f"external GPU evidence is not captured: {case_id}")
        if not isinstance(gpu.get("gpu_uuids"), list) or not gpu["gpu_uuids"]:
            raise ValueError(f"GPU UUID is missing: {case_id}/{process_name}")
        return 1
    if execution_device != "cpu" or model_device != "cpu" or output_device != "cpu":
        raise ValueError(f"CPU case used a non-CPU device: {case_id}/{process_name}")
    return 0


def _verify_case(
    archive: zipfile.ZipFile,
    members: dict[str, zipfile.ZipInfo],
    result: dict[str, Any],
) -> VerifiedCase:
    case_id = result.get("case_id")
    if not isinstance(case_id, str):
        raise ValueError("matrix case_id must be a string")
    match = _CASE_ID.fullmatch(case_id)
    if match is None:
        raise ValueError(f"invalid formal case_id: {case_id}")
    device = match.group(4)
    if result.get("returncode") != 0 or result.get("response_status") != "OK":
        raise ValueError(f"matrix case is not PASS: {case_id}")
    response = _read_json(
        archive,
        members,
        f"cases/{case_id}/response.json",
    )
    if response.get("status") != "OK" or response.get("phase") != "predict":
        raise ValueError(f"provider response is not successful: {case_id}")
    effective = response.get("effective_arguments")
    if not isinstance(effective, dict) or effective.get("actuals_used") is not False:
        raise ValueError(f"actuals boundary is invalid: {case_id}")
    certification = _read_json(
        archive,
        members,
        f"cases/{case_id}/runtime/CERTIFICATION_RESULT.json",
    )
    if certification.get("status") != "PASS":
        raise ValueError(f"runtime certification is not PASS: {case_id}")
    if certification.get("two_process_exact_replay") is not True:
        raise ValueError(f"two-process replay is not certified: {case_id}")
    replay = _read_json(
        archive,
        members,
        f"cases/{case_id}/runtime/REPLAY_COMPARISON.json",
    )
    if replay.get("exact_equal") is not True:
        raise ValueError(f"native replay is not exact: {case_id}")
    gpu_count = 0
    for process_name in ("process-1", "process-2"):
        gpu_count += _verify_process_evidence(
            archive,
            members,
            case_id,
            process_name,
            device,
        )
    return VerifiedCase(
        case_id=case_id,
        device=device,
        response_status="OK",
        replay_exact=True,
        gpu_processes_verified=gpu_count,
    )


def verify_certification_archive(
    archive_path: Path,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    archive_sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    if expected_sha256 is not None and archive_sha256 != expected_sha256:
        raise ValueError(
            f"archive SHA-256 mismatch: expected={expected_sha256} actual={archive_sha256}"
        )
    with zipfile.ZipFile(archive_path) as archive:
        members = _safe_members(archive)
        _verify_embedded_manifest(archive, members)
        _verify_sha256s(archive, members)
        matrix = _read_json(archive, members, "MATRIX_RESULT.json")
        if matrix.get("status") != "PASS" or matrix.get("total_cases") != 90:
            raise ValueError("matrix result is not a complete 90-case PASS")
        if matrix.get("passed_cases") != 90:
            raise ValueError("matrix result passed_cases must be 90")
        if matrix.get("runtime_certified") is not True:
            raise ValueError("matrix result runtime_certified must be true")
        if matrix.get("forecast_accuracy_certified") is not False:
            raise ValueError("runtime archive must not claim forecast accuracy")
        raw_cases = matrix.get("cases")
        if not isinstance(raw_cases, list) or len(raw_cases) != 90:
            raise ValueError("matrix cases must contain 90 results")
        verified = [_verify_case(archive, members, item) for item in raw_cases]
        case_ids = [case.case_id for case in verified]
        if len(set(case_ids)) != 90:
            raise ValueError("matrix case IDs must be unique")
        cpu_cases = sum(case.device == "cpu" for case in verified)
        cuda_cases = sum(case.device == "cuda" for case in verified)
        gpu_processes = sum(case.gpu_processes_verified for case in verified)
        if (cpu_cases, cuda_cases, gpu_processes) != (45, 45, 90):
            raise ValueError(
                "matrix device evidence counts are invalid: "
                f"cpu={cpu_cases} cuda={cuda_cases} gpu_processes={gpu_processes}"
            )
    return {
        "schema_version": 1,
        "status": "VERIFIED",
        "archive_path": str(archive_path.resolve()),
        "archive_sha256": archive_sha256,
        "total_cases": 90,
        "cpu_cases": 45,
        "cuda_cases": 45,
        "gpu_processes_verified": 90,
        "two_process_replay_verified": True,
        "forecast_accuracy_certified": False,
    }

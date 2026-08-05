from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from loto.adapters.timesfm25.contracts import TimesFM25Request, TimesFM25Response
from loto.timesfm25_campaign.certification import judge_gpu_certification

_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def validate_run_id(value: str) -> str:
    """Validate a run identifier before using it as a directory name."""
    if not _SAFE_RUN_ID.fullmatch(value) or value in {".", ".."}:
        raise ValueError(
            "run_id must be 1..128 characters using only letters, digits, '.', '_', or '-'"
        )
    return value


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    """Write UTF-8 text atomically in the destination directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Serialize a JSON object with deterministic formatting."""
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def build_certification_report(
    request: TimesFM25Request,
    response_payload: dict[str, Any] | None,
    *,
    provider_exit_code: int,
    timed_out: bool,
) -> dict[str, Any]:
    """Build a fail-closed runtime certification summary."""
    base: dict[str, Any] = {
        "schema_version": 1,
        "run_id": request.run_id,
        "backend": request.backend.value,
        "repo_id": request.repo_id,
        "revision": request.revision,
        "device_requested": request.device,
        "provider_exit_code": provider_exit_code,
        "timed_out": timed_out,
        "runtime_status": "FAILED",
        "gpu_certification_status": "NOT_EVALUATED",
        "gpu_certification_reasons": [],
    }
    if timed_out:
        base["failure_reason"] = "PROVIDER_TIMEOUT"
        return base
    if provider_exit_code != 0:
        base["failure_reason"] = "PROVIDER_NONZERO_EXIT"
        return base
    if response_payload is None:
        base["failure_reason"] = "PROVIDER_RESPONSE_MISSING"
        return base
    if response_payload.get("status") != "OK":
        base["failure_reason"] = str(
            response_payload.get("message", "PROVIDER_RESPONSE_ERROR")
        )
        base["provider_error_type"] = response_payload.get("error_type")
        return base

    response = TimesFM25Response.model_validate(response_payload)
    verdict = judge_gpu_certification(response.runtime_evidence, response.gpu_evidence)
    base["gpu_certification_status"] = verdict.status
    base["gpu_certification_reasons"] = list(verdict.reasons)
    base["provider_response_valid"] = True
    base["snapshot_path"] = response.artifact_reference.snapshot_path
    base["snapshot_reloaded"] = response.artifact_reference.snapshot_reloaded
    base["model_parameter_device"] = response.runtime_evidence.model_parameter_device
    base["mean_output_device"] = response.runtime_evidence.mean_output_device
    base["quantile_output_device"] = response.runtime_evidence.quantile_output_device
    base["vram_peak_bytes"] = response.gpu_evidence.vram_peak_bytes
    base["external_pid_match"] = response.gpu_evidence.external_pid_match
    base["cpu_fallback"] = (
        response.runtime_evidence.cpu_fallback or response.gpu_evidence.cpu_fallback
    )
    if request.device == "cpu":
        base["runtime_status"] = "VERIFIED_CPU"
    elif verdict.status == "PASS":
        base["runtime_status"] = "VERIFIED_GPU"
    else:
        base["runtime_status"] = "PARTIALLY_VERIFIED_GPU"
    return base


def write_sha256_manifest(
    root: Path,
    *,
    manifest_name: str = "SHA256SUMS",
) -> Path:
    """Seal all current files below root into a deterministic SHA-256 manifest."""
    root = root.resolve()
    manifest = root / manifest_name
    entries: list[str] = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        if path == manifest:
            continue
        relative = path.relative_to(root).as_posix()
        entries.append(f"{sha256_file(path)}  {relative}")
    atomic_write_text(manifest, "\n".join(entries) + ("\n" if entries else ""))
    return manifest


def verify_sha256_manifest(
    root: Path,
    *,
    manifest_name: str = "SHA256SUMS",
) -> tuple[bool, tuple[str, ...]]:
    """Verify every path recorded in a bundle manifest."""
    root = root.resolve()
    manifest = root / manifest_name
    failures: list[str] = []
    recorded_paths: set[str] = set()
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not line:
            continue
        try:
            expected, relative = line.split("  ", 1)
        except ValueError:
            failures.append(f"line-{line_number}:INVALID_FORMAT")
            continue
        if relative in recorded_paths:
            failures.append(f"{relative}:DUPLICATE")
            continue
        recorded_paths.add(relative)
        path = root / relative
        try:
            path.resolve().relative_to(root)
        except ValueError:
            failures.append(f"{relative}:PATH_ESCAPE")
            continue
        if not path.is_file():
            failures.append(f"{relative}:MISSING")
            continue
        actual = sha256_file(path)
        if actual != expected:
            failures.append(f"{relative}:HASH_MISMATCH")
    actual_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != manifest
    }
    for relative in sorted(actual_paths - recorded_paths):
        failures.append(f"{relative}:UNEXPECTED")
    return not failures, tuple(failures)

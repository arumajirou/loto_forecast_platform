"""Atomic evidence bundle writer and strict verifier."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from .argv import build_argv_plan
from .canonical import canonical_json, parse_json_object, sha256_bytes
from .contracts import (
    BackendEvidence,
    EffectiveSandboxEvidence,
    SandboxArgvPlan,
    SandboxExecutionRequest,
    SandboxPolicy,
    SandboxProcessResult,
    SandboxVerificationReport,
)
from .validation import validate_request, verify_effective_evidence

EVIDENCE_FILES = (
    "backend.json",
    "effective.json",
    "plan.json",
    "policy.json",
    "process_result.json",
    "request.json",
    "verification.json",
)


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _json_bytes(value: Any) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def write_evidence_bundle(
    output_dir: Path,
    *,
    policy: SandboxPolicy,
    request: SandboxExecutionRequest,
    backend: BackendEvidence,
    plan: SandboxArgvPlan,
    effective: EffectiveSandboxEvidence,
    verification: SandboxVerificationReport,
    process_result: SandboxProcessResult,
) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("evidence output directory must be absent or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "backend.json": backend,
        "effective.json": effective,
        "plan.json": plan,
        "policy.json": policy,
        "process_result.json": process_result,
        "request.json": request,
        "verification.json": verification,
    }
    manifest_entries: list[dict[str, object]] = []
    for name in EVIDENCE_FILES:
        data = _json_bytes(payloads[name])
        _write_atomic(output_dir / name, data)
        manifest_entries.append(
            {"path": name, "sha256": sha256_bytes(data), "size_bytes": len(data)}
        )
    manifest = {
        "schema_version": "1.0.0",
        "artifact_set": "provider-sandbox-evidence-v1",
        "artifacts": manifest_entries,
        "kernel_isolation_certified": False,
        "runtime_certified": False,
        "security_certified": False,
    }
    manifest_data = _json_bytes(manifest)
    _write_atomic(output_dir / "ARTIFACT_MANIFEST.json", manifest_data)
    sums_entries = manifest_entries + [
        {
            "path": "ARTIFACT_MANIFEST.json",
            "sha256": sha256_bytes(manifest_data),
            "size_bytes": len(manifest_data),
        }
    ]
    sums = "".join(f"{item['sha256']}  {item['path']}\n" for item in sums_entries)
    _write_atomic(output_dir / "SHA256SUMS", sums.encode("utf-8"))


def _load_strict_model(path: Path, model_type: type):
    data = parse_json_object(path.read_text(encoding="utf-8"))
    return model_type.model_validate_json(canonical_json(data))


def _safe_name(value: str) -> str:
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or len(parsed.parts) != 1 or parsed.name != value:
        raise ValueError("manifest path must be a safe top-level relative path")
    return value


def verify_evidence_bundle(output_dir: Path) -> dict[str, object]:
    expected_files = set(EVIDENCE_FILES) | {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
    actual_files = {path.name for path in output_dir.iterdir() if path.is_file()}
    if actual_files != expected_files:
        raise ValueError("evidence file inventory mismatch")
    if any(path.is_symlink() for path in output_dir.iterdir()):
        raise ValueError("symlinks are forbidden in evidence bundles")
    manifest_raw = (output_dir / "ARTIFACT_MANIFEST.json").read_text(encoding="utf-8")
    manifest = parse_json_object(manifest_raw)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("manifest artifacts must be a list")
    seen: set[str] = set()
    for entry in artifacts:
        if not isinstance(entry, dict):
            raise ValueError("manifest entry must be an object")
        name = _safe_name(str(entry.get("path")))
        if name in seen:
            raise ValueError("duplicate manifest path")
        seen.add(name)
        data = (output_dir / name).read_bytes()
        if len(data) != entry.get("size_bytes") or sha256_bytes(data) != entry.get("sha256"):
            raise ValueError(f"artifact integrity mismatch: {name}")
    if seen != set(EVIDENCE_FILES):
        raise ValueError("manifest does not cover exact evidence inventory")
    sums_lines = (output_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    sums: dict[str, str] = {}
    for line in sums_lines:
        digest, separator, name = line.partition("  ")
        if not separator or name in sums:
            raise ValueError("invalid or duplicate SHA256SUMS entry")
        sums[_safe_name(name)] = digest
    if set(sums) != set(EVIDENCE_FILES) | {"ARTIFACT_MANIFEST.json"}:
        raise ValueError("SHA256SUMS inventory mismatch")
    for name, digest in sums.items():
        if sha256_bytes((output_dir / name).read_bytes()) != digest:
            raise ValueError(f"SHA256SUMS mismatch: {name}")
    if any(
        manifest.get(key) is not False
        for key in (
            "kernel_isolation_certified",
            "runtime_certified",
            "security_certified",
        )
    ):
        raise ValueError("foundation bundle cannot claim certification")
    backend = _load_strict_model(output_dir / "backend.json", BackendEvidence)
    effective = _load_strict_model(output_dir / "effective.json", EffectiveSandboxEvidence)
    plan = _load_strict_model(output_dir / "plan.json", SandboxArgvPlan)
    policy = _load_strict_model(output_dir / "policy.json", SandboxPolicy)
    process_result = _load_strict_model(output_dir / "process_result.json", SandboxProcessResult)
    request = _load_strict_model(output_dir / "request.json", SandboxExecutionRequest)
    verification = _load_strict_model(output_dir / "verification.json", SandboxVerificationReport)
    validate_request(policy, request)
    expected_plan = build_argv_plan(policy, request, backend)
    if plan != expected_plan:
        raise ValueError("argv plan does not match policy, request and backend evidence")
    expected_verification = verify_effective_evidence(policy, request, effective)
    if verification != expected_verification:
        raise ValueError("verification report does not match effective evidence")
    if verification.policy_sha256 != policy.policy_sha256:
        raise ValueError("verification policy binding mismatch")
    if verification.effective_evidence_sha256 != effective.evidence_sha256:
        raise ValueError("verification effective-evidence binding mismatch")
    if process_result.result_sha256 == "0" * 64:
        raise ValueError("process result cannot use placeholder identity")
    return {
        "status": "PASS",
        "artifact_count": len(EVIDENCE_FILES),
        "policy_sha256": policy.policy_sha256,
        "verification_status": verification.status.value,
    }

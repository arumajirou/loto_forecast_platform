from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from loto.basicts_campaign.certification import (
    EXPECTED_BASICTS_VERSION,
    EXPECTED_UPSTREAM_REVISION,
    verify_provider_bundle,
)
from loto.basicts_campaign.lock_audit import (
    EXPECTED_DIRECT_DEPENDENCIES,
    EXPECTED_REQUIRES_PYTHON,
    EXPECTED_UV_VERSION,
    verify_workspace_metadata,
)

DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
CHECKSUM_LINE = re.compile(r"^(?P<digest>[0-9a-f]{64})  (?P<path>.+)$")
EXPECTED_EXCLUDE_NEWER = "2026-08-05T00:00:00Z"


class FormalVerificationError(RuntimeError):
    """Raised when a formal P0 evidence bundle is unsafe or inconsistent."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise FormalVerificationError(f"JSON evidence is missing or unsafe: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalVerificationError(f"cannot parse JSON evidence: {path}") from exc
    if not isinstance(payload, dict):
        raise FormalVerificationError(f"JSON evidence must contain an object: {path}")
    return payload


def _safe_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise FormalVerificationError(f"unsafe evidence path: {value!r}")
    path = PurePosixPath(value)
    if not path.parts or path.is_absolute() or path.as_posix() != value:
        raise FormalVerificationError(f"unsafe evidence path: {value!r}")
    if any(COMPONENT_PATTERN.fullmatch(part) is None for part in path.parts):
        raise FormalVerificationError(f"unsafe evidence path: {value!r}")
    return value


def _regular_files(directory: Path) -> dict[str, Path]:
    if directory.is_symlink() or not directory.is_dir():
        raise FormalVerificationError(f"evidence directory is missing or unsafe: {directory}")
    files: dict[str, Path] = {}
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise FormalVerificationError(f"symbolic links are forbidden: {path}")
        if path.is_file():
            relative = path.relative_to(directory).as_posix()
            _safe_relative_path(relative)
            files[relative] = path
    return files


def verify_recursive_sha256(directory: Path) -> dict[str, str]:
    """Verify a recursive portable SHA256SUMS file with an exact file set."""

    files = _regular_files(directory)
    checksum_path = files.get("SHA256SUMS")
    if checksum_path is None:
        raise FormalVerificationError(f"SHA256SUMS is missing: {directory}")
    expected: dict[str, str] = {}
    for line_number, line in enumerate(
        checksum_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        match = CHECKSUM_LINE.fullmatch(line)
        if match is None:
            raise FormalVerificationError(f"invalid SHA256SUMS line {line_number}: {line!r}")
        relative = _safe_relative_path(match.group("path"))
        if relative == "SHA256SUMS":
            raise FormalVerificationError("SHA256SUMS must not hash itself")
        if relative in expected:
            raise FormalVerificationError(f"duplicate SHA256SUMS path: {relative}")
        expected[relative] = match.group("digest")

    actual_names = set(files) - {"SHA256SUMS"}
    if set(expected) != actual_names:
        missing = sorted(actual_names - set(expected))
        unknown = sorted(set(expected) - actual_names)
        raise FormalVerificationError(
            f"SHA256SUMS file set mismatch: missing={missing}, unknown={unknown}"
        )
    for relative, digest in expected.items():
        actual = _sha256(files[relative])
        if actual != digest:
            raise FormalVerificationError(
                f"SHA-256 mismatch for {relative}: expected {digest}, got {actual}"
            )
    return expected


def verify_recursive_manifest(
    directory: Path,
    *,
    manifest_name: str,
    status_name: str,
) -> dict[str, Any]:
    """Verify a recursive manifest against every retained evidence file."""

    files = _regular_files(directory)
    manifest_path = files.get(manifest_name)
    if manifest_path is None:
        raise FormalVerificationError(f"manifest is missing: {directory / manifest_name}")
    manifest = _load_json(manifest_path)
    status = _load_json(directory / status_name)
    if manifest.get("schema_version") != "1.0":
        raise FormalVerificationError(f"unsupported manifest schema: {manifest_name}")
    if manifest.get("status") != status.get("status"):
        raise FormalVerificationError(f"manifest status mismatch: {manifest_name}")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise FormalVerificationError(f"manifest files must be a list: {manifest_name}")

    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise FormalVerificationError(f"manifest entry must be an object: {manifest_name}")
        relative = _safe_relative_path(entry.get("path"))
        if relative in names:
            raise FormalVerificationError(f"duplicate manifest path: {relative}")
        names.add(relative)
        path = files.get(relative)
        if path is None:
            raise FormalVerificationError(f"manifest file is missing: {relative}")
        if entry.get("size_bytes") != path.stat().st_size:
            raise FormalVerificationError(f"manifest size mismatch: {relative}")
        if entry.get("sha256") != _sha256(path):
            raise FormalVerificationError(f"manifest SHA-256 mismatch: {relative}")

    expected = set(files) - {manifest_name, "SHA256SUMS"}
    if names != expected:
        raise FormalVerificationError(
            f"manifest file set mismatch: expected={sorted(expected)}, actual={sorted(names)}"
        )
    return manifest


def _verify_single_checksum(directory: Path, checksum_name: str, target_name: str) -> str:
    _safe_relative_path(checksum_name)
    _safe_relative_path(target_name)
    checksum_path = directory / checksum_name
    target_path = directory / target_name
    if checksum_path.is_symlink() or not checksum_path.is_file():
        raise FormalVerificationError(f"checksum evidence is missing: {checksum_path}")
    if target_path.is_symlink() or not target_path.is_file():
        raise FormalVerificationError(f"checksum target is missing: {target_path}")
    lines = checksum_path.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        raise FormalVerificationError(f"checksum file must contain one line: {checksum_path}")
    match = CHECKSUM_LINE.fullmatch(lines[0])
    if match is None or _safe_relative_path(match.group("path")) != target_name:
        raise FormalVerificationError(f"checksum target mismatch: {checksum_path}")
    actual = _sha256(target_path)
    if match.group("digest") != actual:
        raise FormalVerificationError(f"checksum mismatch: {target_path}")
    return actual


def _require_fields(payload: dict[str, Any], expected: dict[str, Any], context: str) -> None:
    for field, value in expected.items():
        if payload.get(field) != value:
            raise FormalVerificationError(
                f"{context}.{field} mismatch: expected {value!r}, got {payload.get(field)!r}"
            )


def _require_digest(value: Any, context: str) -> str:
    if not isinstance(value, str) or DIGEST_PATTERN.fullmatch(value) is None:
        raise FormalVerificationError(f"invalid SHA-256 for {context}: {value!r}")
    return value


def _verify_commands(
    run_dir: Path,
    commands: Any,
    *,
    expected_phases: tuple[str, ...],
    log_prefix: str,
    require_frozen: bool,
) -> None:
    if not isinstance(commands, list) or len(commands) != len(expected_phases):
        raise FormalVerificationError("command evidence count differs from the contract")
    phases: list[str] = []
    for command in commands:
        if not isinstance(command, dict):
            raise FormalVerificationError("command evidence entry must be an object")
        phase = command.get("phase")
        argv = command.get("command")
        if not isinstance(phase, str) or not isinstance(argv, list):
            raise FormalVerificationError("command phase or argv evidence is invalid")
        if not argv or not all(isinstance(item, str) and item for item in argv):
            raise FormalVerificationError(f"command argv is invalid for phase {phase}")
        if command.get("returncode") != 0:
            raise FormalVerificationError(f"command did not pass: {phase}")
        phases.append(phase)
        for suffix in ("stdout.log", "stderr.log"):
            log = run_dir / log_prefix / f"{phase}.{suffix}"
            if log.is_symlink() or not log.is_file():
                raise FormalVerificationError(f"command log is missing: {log}")
        if require_frozen and phase in {
            "python_lane",
            "identity",
            "validate_config",
            "dlinear_smoke",
        }:
            if "--frozen" not in argv:
                raise FormalVerificationError(f"formal core command is not frozen: {phase}")
    if tuple(phases) != expected_phases:
        raise FormalVerificationError(
            f"command phase order mismatch: expected={expected_phases}, actual={tuple(phases)}"
        )


def _normalise_bundle_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": record.get("operation"),
        "response_sha256": record.get("response_sha256"),
        "manifest_sha256": record.get("manifest_sha256"),
        "file_count": record.get("file_count"),
    }


def _verify_preflight(run_dir: Path, lock_sha256: str) -> dict[str, Any]:
    preflight = run_dir / "preflight"
    audit_path = preflight / "UV_RESOLUTION_AUDIT.json"
    audit_sha256 = _verify_single_checksum(
        preflight,
        "UV_RESOLUTION_AUDIT.json.sha256",
        "UV_RESOLUTION_AUDIT.json",
    )
    audit = _load_json(audit_path)
    _require_fields(
        audit,
        {
            "schema_version": "1.0",
            "status": "PASS",
            "scope": "BASICTS_UV_RESOLUTION_AUDIT",
            "uv_version": EXPECTED_UV_VERSION,
        },
        "resolution_audit",
    )
    lockfile = audit.get("lockfile")
    if not isinstance(lockfile, dict):
        raise FormalVerificationError("resolution_audit.lockfile is missing")
    if _require_digest(lockfile.get("sha256"), "resolution_audit.lockfile") != lock_sha256:
        raise FormalVerificationError("preflight and formal lock SHA-256 differ")

    environment = audit.get("environment")
    if not isinstance(environment, dict):
        raise FormalVerificationError("resolution_audit.environment is missing")
    if environment.get("requires_python") != EXPECTED_REQUIRES_PYTHON:
        raise FormalVerificationError("preflight Python lane differs from the frozen contract")
    if environment.get("uv_version") != EXPECTED_UV_VERSION:
        raise FormalVerificationError("preflight uv version differs from the frozen contract")
    dependencies = environment.get("direct_dependencies")
    if (
        not isinstance(dependencies, list)
        or not all(isinstance(item, str) for item in dependencies)
        or dependencies != sorted(EXPECTED_DIRECT_DEPENDENCIES)
    ):
        raise FormalVerificationError("preflight direct dependencies differ from the contract")
    if environment.get("exclude_newer") != EXPECTED_EXCLUDE_NEWER:
        raise FormalVerificationError("preflight resolution cutoff differs from the contract")
    _require_digest(environment.get("sha256"), "resolution_audit.environment")
    _verify_commands(
        run_dir,
        audit.get("commands"),
        expected_phases=(
            "uv_version",
            "uv_lock",
            "uv_lock_check",
            "uv_sync",
            "uv_workspace_metadata",
        ),
        log_prefix="preflight/logs",
        require_frozen=False,
    )

    metadata_path = preflight / "UV_WORKSPACE_METADATA.json"
    resolution = verify_workspace_metadata(metadata_path)
    recorded_resolution = audit.get("resolution")
    if not isinstance(recorded_resolution, dict):
        raise FormalVerificationError("resolution_audit.resolution is missing")
    if recorded_resolution.get("sha256") != resolution["sha256"]:
        raise FormalVerificationError("workspace metadata SHA-256 differs from the audit")
    for field in (
        "schema_version",
        "python_version",
        "python_implementation",
        "packages",
    ):
        if recorded_resolution.get(field) != resolution[field]:
            raise FormalVerificationError(f"workspace metadata evidence mismatch for {field}")
    return {
        "audit_sha256": audit_sha256,
        "metadata_sha256": resolution["sha256"],
        "python_version": resolution["python_version"],
        "packages": resolution["packages"],
    }


def _verify_core(run_dir: Path, lock_sha256: str) -> dict[str, Any]:
    core = run_dir / "core"
    core_checksums = verify_recursive_sha256(core)
    verify_recursive_manifest(
        core,
        manifest_name="P0_RUN_MANIFEST.json",
        status_name="P0_RUN_STATUS.json",
    )
    status = _load_json(core / "P0_RUN_STATUS.json")
    _require_fields(
        status,
        {
            "schema_version": "1.0",
            "status": "PASS",
            "run_id": "core",
            "environment_lane": "basicts-py311",
            "environment_mode": "FORMAL_PREFLIGHT_REUSE",
            "upstream_revision": EXPECTED_UPSTREAM_REVISION,
            "certificate": "P0_CERTIFICATION_REPORT.json",
        },
        "core_status",
    )
    git_commit = status.get("git_commit")
    if not isinstance(git_commit, str) or COMMIT_PATTERN.fullmatch(git_commit) is None:
        raise FormalVerificationError("core_status.git_commit is invalid")
    _verify_commands(
        run_dir,
        status.get("commands"),
        expected_phases=(
            "git_head",
            "git_status",
            "python_lane",
            "identity",
            "validate_config",
            "dlinear_smoke",
        ),
        log_prefix="core/logs",
        require_frozen=True,
    )
    lockfile = status.get("lockfile")
    if not isinstance(lockfile, dict):
        raise FormalVerificationError("core_status.lockfile is missing")
    if _require_digest(lockfile.get("sha256"), "core_status.lockfile") != lock_sha256:
        raise FormalVerificationError("core and formal lock SHA-256 differ")

    certificate_sha256 = _verify_single_checksum(
        core,
        "P0_CERTIFICATION_REPORT.json.sha256",
        "P0_CERTIFICATION_REPORT.json",
    )
    certificate = _load_json(core / "P0_CERTIFICATION_REPORT.json")
    _require_fields(
        certificate,
        {
            "schema_version": "1.0",
            "status": "PASS",
            "scope": "BASICTS_P0_IDENTITY_CONFIG_DLINEAR_CPU",
            "basicts_version": EXPECTED_BASICTS_VERSION,
            "upstream_revision": EXPECTED_UPSTREAM_REVISION,
        },
        "core_certificate",
    )
    certificate_lock = certificate.get("lockfile")
    if not isinstance(certificate_lock, dict):
        raise FormalVerificationError("core_certificate.lockfile is missing")
    if _require_digest(certificate_lock.get("sha256"), "core_certificate.lockfile") != lock_sha256:
        raise FormalVerificationError("certificate and formal lock SHA-256 differ")

    verified_bundles = [
        verify_provider_bundle(core / "identity", "identity"),
        verify_provider_bundle(core / "validate_config", "validate_config"),
        verify_provider_bundle(core / "dlinear_smoke", "dlinear_smoke"),
    ]
    recorded_bundles = certificate.get("bundles")
    if not isinstance(recorded_bundles, list) or len(recorded_bundles) != 3:
        raise FormalVerificationError("core_certificate.bundles is invalid")
    actual_records = [_normalise_bundle_record(item) for item in verified_bundles]
    recorded_records = [
        _normalise_bundle_record(item) for item in recorded_bundles if isinstance(item, dict)
    ]
    actual = {item["operation"]: item for item in actual_records}
    recorded = {item["operation"]: item for item in recorded_records}
    if (
        len(actual) != len(actual_records)
        or len(recorded) != len(recorded_records)
        or recorded != actual
    ):
        raise FormalVerificationError("provider bundle evidence differs from the certificate")
    return {
        "git_commit": git_commit,
        "certificate_sha256": certificate_sha256,
        "checksum_entries": len(core_checksums),
        "provider_bundles": verified_bundles,
    }


def verify_formal_bundle(run_dir: Path) -> dict[str, Any]:
    """Independently verify one completed formal BasicTS P0 evidence bundle."""

    root = run_dir.resolve()
    top_checksums = verify_recursive_sha256(root)
    verify_recursive_manifest(
        root,
        manifest_name="FORMAL_P0_MANIFEST.json",
        status_name="FORMAL_P0_STATUS.json",
    )
    status = _load_json(root / "FORMAL_P0_STATUS.json")
    _require_fields(
        status,
        {
            "schema_version": "1.0",
            "status": "PASS",
            "scope": "BASICTS_FORMAL_P0",
            "run_id": root.name,
            "uv_version": EXPECTED_UV_VERSION,
            "resolution_audit": "preflight/UV_RESOLUTION_AUDIT.json",
            "core_status": "core/P0_RUN_STATUS.json",
            "core_certificate": "core/P0_CERTIFICATION_REPORT.json",
        },
        "formal_status",
    )
    lock_sha256 = _require_digest(status.get("lock_sha256"), "formal_status.lock")
    preflight = _verify_preflight(root, lock_sha256)
    core = _verify_core(root, lock_sha256)
    expected_certificate = _require_digest(
        status.get("core_certificate_sha256"),
        "formal_status.core_certificate",
    )
    if expected_certificate != core["certificate_sha256"]:
        raise FormalVerificationError("formal and core certificate SHA-256 differ")

    return {
        "schema_version": "1.0",
        "status": "PASS",
        "scope": "BASICTS_FORMAL_P0_EVIDENCE_VERIFICATION",
        "evidence_only": True,
        "run_id": status["run_id"],
        "git_commit": core["git_commit"],
        "uv_version": EXPECTED_UV_VERSION,
        "basicts_version": EXPECTED_BASICTS_VERSION,
        "upstream_revision": EXPECTED_UPSTREAM_REVISION,
        "lock_sha256": lock_sha256,
        "source_bundle": {
            "path": str(root),
            "formal_status_sha256": _sha256(root / "FORMAL_P0_STATUS.json"),
            "formal_manifest_sha256": _sha256(root / "FORMAL_P0_MANIFEST.json"),
            "checksum_entries": len(top_checksums),
        },
        "preflight": preflight,
        "core": core,
        "verified": {
            "recursive_sha256": True,
            "recursive_manifests": True,
            "dependency_metadata": True,
            "lock_cross_links": True,
            "formal_preflight_reuse": True,
            "frozen_core_commands": True,
            "provider_bundles": True,
        },
        "not_certified": [
            "re-execution of dependency installation or model inference",
            "accuracy improvement or baseline superiority",
            "GPU, AMP, DDP, Holdout, or Prospective execution",
            "shared worker, catalog, CLI, MLflow, or PostgreSQL integration",
        ],
    }


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        temporary_path.write_text(text, encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _output_path(run_dir: Path, output: Path | None) -> Path:
    resolved_run = run_dir.resolve()
    candidate = (
        output.resolve()
        if output is not None
        else resolved_run.parent / f"{resolved_run.name}.verification.json"
    )
    if candidate == resolved_run or candidate.is_relative_to(resolved_run):
        raise FormalVerificationError("verification output must be outside the source bundle")
    checksum = candidate.with_suffix(candidate.suffix + ".sha256")
    if candidate.is_symlink() or checksum.is_symlink():
        raise FormalVerificationError("verification output path is a symbolic link")
    if candidate.exists() or checksum.exists():
        raise FormalVerificationError(f"verification output already exists: {candidate}")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a formal BasicTS P0 evidence bundle")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify_formal_bundle(args.run_dir)
    output = _output_path(args.run_dir, args.output)
    _atomic_write_text(
        output,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write_text(
        output.with_suffix(output.suffix + ".sha256"),
        f"{_sha256(output)}  {output.name}\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"BASICTS_FORMAL_P0_VERIFICATION=PASS\nREPORT={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

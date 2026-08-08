from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from loto.basicts_campaign import formal_verification
from loto.basicts_campaign.formal_verification import (
    FormalVerificationError,
    _output_path,
    verify_formal_bundle,
)
from loto.basicts_campaign.lock_audit import (
    EXPECTED_DIRECT_DEPENDENCIES,
    EXPECTED_UPSTREAM_REVISION,
)

LOCK_SHA256 = "1" * 64
GIT_COMMIT = "a" * 40


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_bundle(root: Path, manifest_name: str, status: str) -> None:
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).as_posix() not in {manifest_name, "SHA256SUMS"}
    )
    _write_json(
        root / manifest_name,
        {
            "schema_version": "1.0",
            "status": status,
            "files": [
                {
                    "path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
                for path in files
            ],
        },
    )
    hashed = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).as_posix() != "SHA256SUMS"
    )
    (root / "SHA256SUMS").write_text(
        "".join(f"{_sha256(path)}  {path.relative_to(root).as_posix()}\n" for path in hashed),
        encoding="utf-8",
    )


def _commands(
    run_dir: Path,
    *,
    phases: tuple[str, ...],
    log_prefix: str,
    frozen: bool,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for phase in phases:
        log_dir = run_dir / log_prefix
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout = log_dir / f"{phase}.stdout.log"
        stderr = log_dir / f"{phase}.stderr.log"
        stdout.write_text("ok\n", encoding="utf-8")
        stderr.write_text("", encoding="utf-8")
        argv = ["uv", phase]
        if frozen and phase in {
            "python_lane",
            "identity",
            "validate_config",
            "dlinear_smoke",
        }:
            argv.append("--frozen")
        evidence.append(
            {
                "phase": phase,
                "command": argv,
                "returncode": 0,
                "stdout_path": str(stdout),
                "stderr_path": str(stderr),
            }
        )
    return evidence


def _provider_record(operation: str) -> dict[str, Any]:
    return {
        "operation": operation,
        "directory": f"/original/core/{operation}",
        "response_sha256": operation[0] * 64,
        "manifest_sha256": operation[-1] * 64,
        "file_count": 3,
    }


def _build_bundle(
    tmp_path: Path,
    *,
    core_lock_sha256: str = LOCK_SHA256,
    environment_mode: str = "FORMAL_PREFLIGHT_REUSE",
    core_frozen: bool = True,
) -> tuple[Path, dict[str, Any]]:
    run_dir = tmp_path / "run-1"
    preflight = run_dir / "preflight"
    core = run_dir / "core"
    preflight.mkdir(parents=True)
    core.mkdir()

    metadata = preflight / "UV_WORKSPACE_METADATA.json"
    metadata.write_text("{}\n", encoding="utf-8")
    resolution = {
        "path": str(metadata),
        "sha256": _sha256(metadata),
        "schema_version": "preview",
        "python_version": "3.11.13",
        "python_implementation": "cpython",
        "packages": {"basicts": {"version": "1.1.0"}},
    }
    preflight_commands = _commands(
        run_dir,
        phases=(
            "uv_version",
            "uv_lock",
            "uv_lock_check",
            "uv_sync",
            "uv_workspace_metadata",
        ),
        log_prefix="preflight/logs",
        frozen=False,
    )
    _write_json(
        preflight / "UV_RESOLUTION_AUDIT.json",
        {
            "schema_version": "1.0",
            "status": "PASS",
            "scope": "BASICTS_UV_RESOLUTION_AUDIT",
            "uv_version": "0.12.0",
            "environment": {
                "sha256": "3" * 64,
                "requires_python": ">=3.11,<3.12",
                "uv_version": "0.12.0",
                "exclude_newer": "2026-08-05T00:00:00Z",
                "direct_dependencies": sorted(EXPECTED_DIRECT_DEPENDENCIES),
            },
            "lockfile": {"sha256": LOCK_SHA256},
            "resolution": resolution,
            "commands": preflight_commands,
        },
    )
    audit = preflight / "UV_RESOLUTION_AUDIT.json"
    (preflight / "UV_RESOLUTION_AUDIT.json.sha256").write_text(
        f"{_sha256(audit)}  UV_RESOLUTION_AUDIT.json\n",
        encoding="utf-8",
    )

    records = [
        _provider_record("identity"),
        _provider_record("validate_config"),
        _provider_record("dlinear_smoke"),
    ]
    _write_json(
        core / "P0_CERTIFICATION_REPORT.json",
        {
            "schema_version": "1.0",
            "status": "PASS",
            "scope": "BASICTS_P0_IDENTITY_CONFIG_DLINEAR_CPU",
            "basicts_version": "1.1.0",
            "upstream_revision": EXPECTED_UPSTREAM_REVISION,
            "lockfile": {"sha256": core_lock_sha256},
            "bundles": records,
        },
    )
    certificate = core / "P0_CERTIFICATION_REPORT.json"
    (core / "P0_CERTIFICATION_REPORT.json.sha256").write_text(
        f"{_sha256(certificate)}  P0_CERTIFICATION_REPORT.json\n",
        encoding="utf-8",
    )
    core_commands = _commands(
        run_dir,
        phases=(
            "git_head",
            "git_status",
            "python_lane",
            "identity",
            "validate_config",
            "dlinear_smoke",
        ),
        log_prefix="core/logs",
        frozen=core_frozen,
    )
    _write_json(
        core / "P0_RUN_STATUS.json",
        {
            "schema_version": "1.0",
            "status": "PASS",
            "run_id": "core",
            "git_commit": GIT_COMMIT,
            "environment_lane": "basicts-py311",
            "environment_mode": environment_mode,
            "upstream_revision": EXPECTED_UPSTREAM_REVISION,
            "lockfile": {"sha256": core_lock_sha256},
            "certificate": "P0_CERTIFICATION_REPORT.json",
            "commands": core_commands,
        },
    )
    _write_bundle(core, "P0_RUN_MANIFEST.json", "PASS")

    _write_json(
        run_dir / "FORMAL_P0_STATUS.json",
        {
            "schema_version": "1.0",
            "status": "PASS",
            "scope": "BASICTS_FORMAL_P0",
            "run_id": run_dir.name,
            "uv_version": "0.12.0",
            "lock_sha256": LOCK_SHA256,
            "resolution_audit": "preflight/UV_RESOLUTION_AUDIT.json",
            "core_status": "core/P0_RUN_STATUS.json",
            "core_certificate": "core/P0_CERTIFICATION_REPORT.json",
            "core_certificate_sha256": _sha256(certificate),
        },
    )
    _write_bundle(run_dir, "FORMAL_P0_MANIFEST.json", "PASS")
    return run_dir, resolution


def _patch_external_verifiers(
    monkeypatch: pytest.MonkeyPatch,
    resolution: dict[str, Any],
) -> None:
    monkeypatch.setattr(
        formal_verification,
        "verify_workspace_metadata",
        lambda path: resolution,
    )
    monkeypatch.setattr(
        formal_verification,
        "verify_provider_bundle",
        lambda directory, operation: {
            **_provider_record(operation),
            "directory": str(directory),
        },
    )


def test_verify_formal_bundle_accepts_consistent_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, resolution = _build_bundle(tmp_path)
    _patch_external_verifiers(monkeypatch, resolution)

    report = verify_formal_bundle(run_dir)

    assert report["status"] == "PASS"
    assert report["lock_sha256"] == LOCK_SHA256
    assert report["core"]["git_commit"] == GIT_COMMIT
    assert report["verified"]["formal_preflight_reuse"] is True


def test_verify_formal_bundle_rejects_tampered_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, resolution = _build_bundle(tmp_path)
    _patch_external_verifiers(monkeypatch, resolution)
    (run_dir / "preflight" / "UV_WORKSPACE_METADATA.json").write_text(
        "tampered\n",
        encoding="utf-8",
    )

    with pytest.raises(FormalVerificationError, match="SHA-256 mismatch"):
        verify_formal_bundle(run_dir)


def test_verify_formal_bundle_rejects_lock_cross_link_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, resolution = _build_bundle(tmp_path, core_lock_sha256="2" * 64)
    _patch_external_verifiers(monkeypatch, resolution)

    with pytest.raises(FormalVerificationError, match="core and formal lock"):
        verify_formal_bundle(run_dir)


def test_verify_formal_bundle_requires_preflight_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, resolution = _build_bundle(tmp_path, environment_mode="STANDALONE_RESOLUTION")
    _patch_external_verifiers(monkeypatch, resolution)

    with pytest.raises(FormalVerificationError, match="environment_mode mismatch"):
        verify_formal_bundle(run_dir)


def test_verify_formal_bundle_requires_frozen_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, resolution = _build_bundle(tmp_path, core_frozen=False)
    _patch_external_verifiers(monkeypatch, resolution)

    with pytest.raises(FormalVerificationError, match="not frozen"):
        verify_formal_bundle(run_dir)


def test_verify_formal_bundle_rejects_unsafe_checksum_path(tmp_path: Path) -> None:
    run_dir, _ = _build_bundle(tmp_path)
    checksum = run_dir / "SHA256SUMS"
    lines = checksum.read_text(encoding="utf-8").splitlines()
    digest, _ = lines[0].split("  ", maxsplit=1)
    lines[0] = f"{digest}  ../escape"
    checksum.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(FormalVerificationError, match="unsafe evidence path"):
        verify_formal_bundle(run_dir)


def test_output_path_must_be_outside_bundle(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    with pytest.raises(FormalVerificationError, match="outside the source bundle"):
        _output_path(run_dir, run_dir / "verification.json")

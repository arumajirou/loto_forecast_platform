from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loto.basicts_campaign.lock_audit import (
    EXPECTED_UV_VERSION,
    verify_environment_pyproject,
    verify_workspace_metadata,
)
from loto.basicts_campaign.orchestration import (
    ENVIRONMENT_LANE,
    CommandExecutionError,
    CommandResult,
    _atomic_write_text,
    _regular_run_files,
    _run_checked,
    _safe_run_id,
    _sha256,
    _write_json,
    run_p0,
)

UV_VERSION_PATTERN = re.compile(r"^uv (?P<version>[0-9]+(?:\.[0-9]+){2})(?: .*)?$")


class FormalP0Error(RuntimeError):
    """Raised when the formal BasicTS P0 sequence cannot be certified."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _uv_version(result: CommandResult) -> str:
    value = Path(result.stdout_path).read_text(encoding="utf-8").strip()
    match = UV_VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise FormalP0Error(f"uv --version returned an unexpected value: {value!r}")
    version = match.group("version")
    if version != EXPECTED_UV_VERSION:
        raise FormalP0Error(f"uv version mismatch: expected {EXPECTED_UV_VERSION}, got {version}")
    return version


def _copy_json_stdout(result: CommandResult, destination: Path) -> None:
    source = Path(result.stdout_path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalP0Error(f"phase {result.phase} did not emit JSON") from exc
    if not isinstance(payload, dict):
        raise FormalP0Error(f"phase {result.phase} JSON must contain an object")
    _write_json(destination, payload)


def _write_formal_bundle(staging_dir: Path, payload: dict[str, Any]) -> None:
    _write_json(staging_dir / "FORMAL_P0_STATUS.json", payload)
    excluded = {"FORMAL_P0_MANIFEST.json", "SHA256SUMS"}
    files = [
        path
        for path in _regular_run_files(staging_dir)
        if path.relative_to(staging_dir).as_posix() not in excluded
    ]
    manifest = {
        "schema_version": "1.0",
        "status": payload["status"],
        "files": [
            {
                "path": path.relative_to(staging_dir).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in files
        ],
    }
    _write_json(staging_dir / "FORMAL_P0_MANIFEST.json", manifest)
    hashed = [
        path
        for path in _regular_run_files(staging_dir)
        if path.relative_to(staging_dir).as_posix() != "SHA256SUMS"
    ]
    _atomic_write_text(
        staging_dir / "SHA256SUMS",
        "".join(
            f"{_sha256(path)}  {path.relative_to(staging_dir).as_posix()}\n" for path in hashed
        ),
    )


def _finalize(staging_dir: Path, final_dir: Path) -> Path:
    if final_dir.exists():
        raise FormalP0Error(f"formal run directory already exists: {final_dir}")
    os.replace(staging_dir, final_dir)
    return final_dir


def run_formal_p0(
    *,
    repo_root: Path,
    artifacts_root: Path,
    run_id: str,
    timeout_seconds: int,
) -> Path:
    """Run dependency preflight and core P0 before atomically publishing a formal bundle."""

    root = repo_root.resolve()
    run_name = _safe_run_id(run_id)
    destination_root = artifacts_root.resolve()
    final_dir = destination_root / run_name
    staging_dir = destination_root / f".{run_name}.staging"
    if final_dir.exists() or staging_dir.exists():
        raise FormalP0Error("formal run or staging directory already exists")
    staging_dir.mkdir(parents=True)
    preflight_dir = staging_dir / "preflight"
    preflight_dir.mkdir()
    log_dir = preflight_dir / "logs"
    log_dir.mkdir()
    started_at = _utc_now()
    commands: list[CommandResult] = []
    phase = "prepare"
    environment_dir = root / "environments" / ENVIRONMENT_LANE
    pyproject = environment_dir / "pyproject.toml"
    lockfile = environment_dir / "uv.lock"
    try:
        uv = shutil.which("uv")
        if uv is None:
            raise FormalP0Error("uv executable was not found")
        environment_evidence = verify_environment_pyproject(pyproject)
        env = os.environ.copy()

        phase = "uv_version"
        result = _run_checked(
            phase=phase,
            command=(uv, "--version"),
            cwd=root,
            env=env,
            log_dir=log_dir,
            timeout_seconds=timeout_seconds,
        )
        commands.append(result)
        uv_version = _uv_version(result)

        phase = "uv_lock"
        result = _run_checked(
            phase=phase,
            command=(
                uv,
                "lock",
                "--project",
                str(environment_dir),
                "--python",
                "3.11",
            ),
            cwd=root,
            env=env,
            log_dir=log_dir,
            timeout_seconds=timeout_seconds,
        )
        commands.append(result)

        phase = "uv_lock_check"
        result = _run_checked(
            phase=phase,
            command=(uv, "lock", "--check", "--project", str(environment_dir)),
            cwd=root,
            env=env,
            log_dir=log_dir,
            timeout_seconds=timeout_seconds,
        )
        commands.append(result)

        phase = "uv_sync"
        result = _run_checked(
            phase=phase,
            command=(
                uv,
                "sync",
                "--frozen",
                "--project",
                str(environment_dir),
                "--python",
                "3.11",
            ),
            cwd=root,
            env=env,
            log_dir=log_dir,
            timeout_seconds=timeout_seconds,
        )
        commands.append(result)

        phase = "uv_workspace_metadata"
        result = _run_checked(
            phase=phase,
            command=(
                uv,
                "workspace",
                "metadata",
                "--locked",
                "--project",
                str(environment_dir),
            ),
            cwd=root,
            env=env,
            log_dir=log_dir,
            timeout_seconds=timeout_seconds,
        )
        commands.append(result)
        metadata_path = preflight_dir / "UV_WORKSPACE_METADATA.json"
        _copy_json_stdout(result, metadata_path)
        resolution_evidence = verify_workspace_metadata(metadata_path)
        lock_sha256 = _sha256(lockfile)
        audit = {
            "schema_version": "1.0",
            "status": "PASS",
            "scope": "BASICTS_UV_RESOLUTION_AUDIT",
            "uv_version": uv_version,
            "environment": environment_evidence,
            "lockfile": {
                "path": str(lockfile),
                "size_bytes": lockfile.stat().st_size,
                "sha256": lock_sha256,
            },
            "resolution": resolution_evidence,
            "commands": [asdict(command) for command in commands],
        }
        audit_path = preflight_dir / "UV_RESOLUTION_AUDIT.json"
        _write_json(audit_path, audit)
        _atomic_write_text(
            preflight_dir / "UV_RESOLUTION_AUDIT.json.sha256",
            f"{_sha256(audit_path)}  {audit_path.name}\n",
        )

        phase = "core_p0"
        core_dir = run_p0(
            repo_root=root,
            artifacts_root=staging_dir,
            run_id="core",
            timeout_seconds=timeout_seconds,
        )
        if _sha256(lockfile) != lock_sha256:
            raise FormalP0Error("uv.lock changed between preflight and core P0")
        core_status = json.loads((core_dir / "P0_RUN_STATUS.json").read_text(encoding="utf-8"))
        if core_status.get("status") != "PASS":
            raise FormalP0Error("core P0 did not record PASS")
        core_report = core_dir / "P0_CERTIFICATION_REPORT.json"
        if not core_report.is_file():
            raise FormalP0Error("core P0 certification report is missing")

        payload = {
            "schema_version": "1.0",
            "status": "PASS",
            "scope": "BASICTS_FORMAL_P0",
            "run_id": run_name,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "repo_root": str(root),
            "uv_version": uv_version,
            "lock_sha256": lock_sha256,
            "resolution_audit": "preflight/UV_RESOLUTION_AUDIT.json",
            "core_status": "core/P0_RUN_STATUS.json",
            "core_certificate": "core/P0_CERTIFICATION_REPORT.json",
            "core_certificate_sha256": _sha256(core_report),
        }
        _write_formal_bundle(staging_dir, payload)
        return _finalize(staging_dir, final_dir)
    except Exception as exc:
        if isinstance(exc, CommandExecutionError):
            commands.append(exc.result)
        payload = {
            "schema_version": "1.0",
            "status": "FAILED",
            "scope": "BASICTS_FORMAL_P0",
            "run_id": run_name,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "repo_root": str(root),
            "failed_phase": phase,
            "commands": [asdict(command) for command in commands],
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
        _write_formal_bundle(staging_dir, payload)
        _finalize(staging_dir, final_dir)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the formal BasicTS P0 sequence")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=Path("artifacts/basicts/formal-p0"),
    )
    parser.add_argument(
        "--run-id",
        default=datetime.now(UTC).strftime("basicts-formal-p0-%Y%m%d-%H%M%S"),
    )
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.timeout_seconds < 1:
        raise SystemExit("--timeout-seconds must be positive")
    try:
        run_dir = run_formal_p0(
            repo_root=args.repo_root,
            artifacts_root=args.artifacts_root,
            run_id=args.run_id,
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:
        print(
            f"BASICTS_FORMAL_P0_STATUS=FAILED\nERROR={type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    print(f"BASICTS_FORMAL_P0_STATUS=PASS\nRUN_DIR={run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

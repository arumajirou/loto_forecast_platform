from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from loto.basicts_campaign.certification import (
    EXPECTED_UPSTREAM_REVISION,
    certify_p0,
    verify_lockfile,
)

ENVIRONMENT_LANE = "basicts-py311"
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUEST_SPECS = (
    ("identity", "identity.json"),
    ("validate_config", "validate_config.json"),
    ("dlinear_smoke", "dlinear_smoke.json"),
)


class OrchestrationError(RuntimeError):
    """Raised when the target-host P0 run cannot be completed safely."""


@dataclass(frozen=True)
class CommandResult:
    phase: str
    command: tuple[str, ...]
    returncode: int
    stdout_path: str
    stderr_path: str


class CommandExecutionError(OrchestrationError):
    """Retain the failed command result so the run manifest remains diagnostic."""

    def __init__(self, message: str, result: CommandResult) -> None:
        super().__init__(message)
        self.result = result


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
    )
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        temporary_path.write_text(text, encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _safe_run_id(value: str) -> str:
    allowed = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
    if not value or any(character not in allowed for character in value):
        raise OrchestrationError("run_id must contain only letters, numbers, dash, or underscore")
    return value


def _require_repo_root(repo_root: Path) -> Path:
    resolved = repo_root.resolve()
    required = (
        resolved / "environments" / ENVIRONMENT_LANE / "pyproject.toml",
        resolved / "scripts" / "run_basicts_provider.py",
        resolved / "configs" / "basicts_campaign" / "identity.json",
        resolved / "configs" / "basicts_campaign" / "validate_config.json",
        resolved / "configs" / "basicts_campaign" / "dlinear_smoke.json",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise OrchestrationError(f"repository root is incomplete: missing={missing}")
    return resolved


def _prepend_pythonpath(env: dict[str, str], src_dir: Path) -> None:
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(src_dir) if not current else f"{src_dir}{os.pathsep}{current}"


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _run_checked(
    *,
    phase: str,
    command: Sequence[str],
    cwd: Path,
    env: dict[str, str],
    log_dir: Path,
    timeout_seconds: int,
) -> CommandResult:
    if not command or any(not isinstance(part, str) or not part for part in command):
        raise OrchestrationError(f"invalid command for phase {phase}")
    stdout_path = log_dir / f"{phase}.stdout.log"
    stderr_path = log_dir / f"{phase}.stderr.log"
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        _atomic_write_text(stdout_path, _timeout_text(exc.stdout))
        _atomic_write_text(stderr_path, _timeout_text(exc.stderr))
        result = CommandResult(
            phase=phase,
            command=tuple(command),
            returncode=-1,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
        )
        raise CommandExecutionError(
            f"phase {phase} exceeded timeout_seconds={timeout_seconds}",
            result,
        ) from exc
    _atomic_write_text(stdout_path, completed.stdout)
    _atomic_write_text(stderr_path, completed.stderr)
    result = CommandResult(
        phase=phase,
        command=tuple(command),
        returncode=completed.returncode,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )
    if completed.returncode != 0:
        raise CommandExecutionError(
            f"phase {phase} failed with returncode={completed.returncode}; stderr={stderr_path}",
            result,
        )
    return result


def _prepare_requests(repo_root: Path, run_dir: Path) -> dict[str, Path]:
    request_dir = run_dir / "requests"
    request_dir.mkdir(parents=True, exist_ok=False)
    prepared: dict[str, Path] = {}
    for operation, filename in REQUEST_SPECS:
        source = repo_root / "configs" / "basicts_campaign" / filename
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("operation") != operation:
            raise OrchestrationError(f"request operation mismatch: {source}")
        payload["output_dir"] = str(run_dir / operation)
        destination = request_dir / filename
        _write_json(destination, payload)
        prepared[operation] = destination
    return prepared


def _regular_run_files(run_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in run_dir.rglob("*"):
        if path.is_symlink():
            raise OrchestrationError(f"symbolic links are forbidden in P0 evidence: {path}")
        if path.is_file():
            files.append(path)
    return sorted(files)


def _write_portable_bundle(run_dir: Path, payload: dict[str, Any]) -> None:
    _write_json(run_dir / "P0_RUN_STATUS.json", payload)
    excluded = {"P0_RUN_MANIFEST.json", "SHA256SUMS"}
    files = [
        path
        for path in _regular_run_files(run_dir)
        if path.relative_to(run_dir).as_posix() not in excluded
    ]
    manifest = {
        "schema_version": "1.0",
        "status": payload["status"],
        "files": [
            {
                "path": path.relative_to(run_dir).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in files
        ],
    }
    _write_json(run_dir / "P0_RUN_MANIFEST.json", manifest)
    hashed = [
        path
        for path in _regular_run_files(run_dir)
        if path.relative_to(run_dir).as_posix() != "SHA256SUMS"
    ]
    _atomic_write_text(
        run_dir / "SHA256SUMS",
        "".join(f"{_sha256(path)}  {path.relative_to(run_dir).as_posix()}\n" for path in hashed),
    )


def _request_evidence(requests: dict[str, Path]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for operation, path in requests.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        evidence.append(
            {
                "operation": operation,
                "path": str(path),
                "sha256": _sha256(path),
                "seed": payload.get("seed"),
            }
        )
    return evidence


def _read_git_commit(result: CommandResult) -> str:
    commit = Path(result.stdout_path).read_text(encoding="utf-8").strip()
    if COMMIT_PATTERN.fullmatch(commit) is None:
        raise OrchestrationError(f"git rev-parse returned an invalid commit: {commit!r}")
    return commit


def _require_clean_git(result: CommandResult) -> None:
    status = Path(result.stdout_path).read_text(encoding="utf-8")
    if status.strip():
        raise OrchestrationError("tracked repository changes must be committed before P0 execution")


def _prepared_lock_sha256(artifacts_root: Path, lockfile: Path) -> str | None:
    """Read a formal preflight lock digest when core P0 is nested under it."""

    audit_path = artifacts_root.resolve() / "preflight" / "UV_RESOLUTION_AUDIT.json"
    if not audit_path.exists():
        return None
    if audit_path.is_symlink() or not audit_path.is_file():
        raise OrchestrationError(f"invalid formal preflight audit: {audit_path}")
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OrchestrationError(f"cannot read formal preflight audit: {audit_path}") from exc
    if not isinstance(audit, dict) or audit.get("status") != "PASS":
        raise OrchestrationError("formal preflight audit did not record PASS")
    lock_record = audit.get("lockfile")
    if not isinstance(lock_record, dict):
        raise OrchestrationError("formal preflight lockfile evidence is missing")
    expected = lock_record.get("sha256")
    if not isinstance(expected, str) or SHA256_PATTERN.fullmatch(expected) is None:
        raise OrchestrationError("formal preflight lock SHA-256 is invalid")
    actual = _sha256(lockfile)
    if actual != expected:
        raise OrchestrationError(
            f"uv.lock changed after formal preflight: expected {expected}, got {actual}"
        )
    return expected


def _prepare_environment(
    *,
    uv: str,
    root: Path,
    environment_dir: Path,
    lockfile: Path,
    artifacts_root: Path,
    env: dict[str, str],
    log_dir: Path,
    timeout_seconds: int,
    commands: list[CommandResult],
) -> tuple[dict[str, Any], str]:
    prepared_sha256 = _prepared_lock_sha256(artifacts_root, lockfile)
    if prepared_sha256 is not None:
        return verify_lockfile(lockfile), "FORMAL_PREFLIGHT_REUSE"

    commands.append(
        _run_checked(
            phase="uv_lock",
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
    )
    lock_evidence = verify_lockfile(lockfile)
    commands.append(
        _run_checked(
            phase="uv_sync",
            command=(
                uv,
                "sync",
                "--project",
                str(environment_dir),
                "--frozen",
                "--python",
                "3.11",
            ),
            cwd=root,
            env=env,
            log_dir=log_dir,
            timeout_seconds=timeout_seconds,
        )
    )
    return lock_evidence, "STANDALONE_RESOLUTION"


def run_p0(
    *,
    repo_root: Path,
    artifacts_root: Path,
    run_id: str,
    timeout_seconds: int,
) -> Path:
    """Resolve, execute, and certify one immutable BasicTS P0 target-host run."""

    root = _require_repo_root(repo_root)
    run_name = _safe_run_id(run_id)
    artifacts_root_resolved = artifacts_root.resolve()
    run_dir = artifacts_root_resolved / run_name
    if run_dir.exists():
        raise OrchestrationError(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    log_dir = run_dir / "logs"
    log_dir.mkdir()
    started_at = _utc_now()
    commands: list[CommandResult] = []
    phase = "prepare"
    environment_mode: str | None = None
    expected_lock_sha256: str | None = None
    try:
        uv = shutil.which("uv")
        git = shutil.which("git")
        if uv is None:
            raise OrchestrationError("uv executable was not found")
        if git is None:
            raise OrchestrationError("git executable was not found")
        requests = _prepare_requests(root, run_dir)
        request_evidence = _request_evidence(requests)
        environment_dir = root / "environments" / ENVIRONMENT_LANE
        lockfile = environment_dir / "uv.lock"
        env = os.environ.copy()
        env["BASICTS_UPSTREAM_REVISION"] = EXPECTED_UPSTREAM_REVISION
        _prepend_pythonpath(env, root / "src")

        phase = "git_head"
        git_head = _run_checked(
            phase=phase,
            command=(git, "rev-parse", "HEAD"),
            cwd=root,
            env=env,
            log_dir=log_dir,
            timeout_seconds=timeout_seconds,
        )
        commands.append(git_head)
        git_commit = _read_git_commit(git_head)

        phase = "git_status"
        git_status = _run_checked(
            phase=phase,
            command=(git, "status", "--porcelain", "--untracked-files=no"),
            cwd=root,
            env=env,
            log_dir=log_dir,
            timeout_seconds=timeout_seconds,
        )
        commands.append(git_status)
        _require_clean_git(git_status)

        phase = "environment_prepare"
        lock_evidence, environment_mode = _prepare_environment(
            uv=uv,
            root=root,
            environment_dir=environment_dir,
            lockfile=lockfile,
            artifacts_root=artifacts_root_resolved,
            env=env,
            log_dir=log_dir,
            timeout_seconds=timeout_seconds,
            commands=commands,
        )
        expected_lock_sha256 = lock_evidence["sha256"]

        phase = "python_lane"
        commands.append(
            _run_checked(
                phase=phase,
                command=(
                    uv,
                    "run",
                    "--project",
                    str(environment_dir),
                    "--frozen",
                    "--python",
                    "3.11",
                    "python",
                    "-c",
                    "import sys; assert sys.version_info[:2] == (3, 11); print(sys.version)",
                ),
                cwd=root,
                env=env,
                log_dir=log_dir,
                timeout_seconds=timeout_seconds,
            )
        )

        for operation, _ in REQUEST_SPECS:
            phase = operation
            commands.append(
                _run_checked(
                    phase=phase,
                    command=(
                        uv,
                        "run",
                        "--project",
                        str(environment_dir),
                        "--frozen",
                        "--python",
                        "3.11",
                        "python",
                        str(root / "scripts" / "run_basicts_provider.py"),
                        "--request",
                        str(requests[operation]),
                    ),
                    cwd=root,
                    env=env,
                    log_dir=log_dir,
                    timeout_seconds=timeout_seconds,
                )
            )

        phase = "lock_immutability"
        actual_lock_sha256 = _sha256(lockfile)
        if actual_lock_sha256 != expected_lock_sha256:
            raise OrchestrationError(
                "uv.lock changed during core P0: "
                f"expected {expected_lock_sha256}, got {actual_lock_sha256}"
            )

        phase = "certification"
        certificate = certify_p0(
            lockfile=lockfile,
            identity_dir=run_dir / "identity",
            config_dir=run_dir / "validate_config",
            dlinear_dir=run_dir / "dlinear_smoke",
        )
        report_path = run_dir / "P0_CERTIFICATION_REPORT.json"
        _write_json(report_path, certificate)
        _atomic_write_text(
            run_dir / "P0_CERTIFICATION_REPORT.json.sha256",
            f"{_sha256(report_path)}  {report_path.name}\n",
        )
        payload = {
            "schema_version": "1.0",
            "status": "PASS",
            "scope": certificate["scope"],
            "run_id": run_name,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "repo_root": str(root),
            "git_commit": git_commit,
            "environment_lane": ENVIRONMENT_LANE,
            "environment_mode": environment_mode,
            "upstream_revision": EXPECTED_UPSTREAM_REVISION,
            "lockfile": lock_evidence,
            "requests": request_evidence,
            "commands": [asdict(result) for result in commands],
            "certificate": report_path.name,
        }
        _write_portable_bundle(run_dir, payload)
        return run_dir
    except Exception as exc:
        if isinstance(exc, CommandExecutionError):
            commands.append(exc.result)
        payload = {
            "schema_version": "1.0",
            "status": "FAILED",
            "run_id": run_name,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "repo_root": str(root),
            "environment_lane": ENVIRONMENT_LANE,
            "environment_mode": environment_mode,
            "upstream_revision": EXPECTED_UPSTREAM_REVISION,
            "expected_lock_sha256": expected_lock_sha256,
            "failed_phase": phase,
            "commands": [asdict(result) for result in commands],
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
        _write_portable_bundle(run_dir, payload)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and certify BasicTS P0 on a target host")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=Path("artifacts/basicts/p0-certification"),
    )
    parser.add_argument(
        "--run-id",
        default=datetime.now(UTC).strftime("%Y%m%d-%H%M%S"),
    )
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.timeout_seconds < 1:
        raise SystemExit("--timeout-seconds must be positive")
    try:
        run_dir = run_p0(
            repo_root=args.repo_root,
            artifacts_root=args.artifacts_root,
            run_id=args.run_id,
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:
        print(
            f"BASICTS_P0_STATUS=FAILED\nERROR={type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    print(f"BASICTS_P0_STATUS=PASS\nRUN_DIR={run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

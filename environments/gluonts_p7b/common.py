from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STAGES = (
    "preflight",
    "compat_bootstrap",
    "latest_bootstrap",
    "audit",
    "finalize",
)
TERMINAL_STAGE_STATES = {
    "COMPLETED",
    "TIMED_OUT",
    "INTERRUPTED",
    "FAILED_TO_START",
    "SKIPPED",
}
SOURCE_PATHS = (
    "environments/gluonts-p7-target-machine.sh",
    "environments/gluonts-p7b-target-machine.sh",
    "environments/gluonts-p7b-supervisor.py",
    "environments/gluonts_p7b/__init__.py",
    "environments/gluonts_p7b/common.py",
    "environments/gluonts_p7b/process.py",
    "environments/gluonts_p7b/stages.py",
    "environments/gluonts_p7b/main.py",
    "environments/gluonts-compat/p6_bootstrap_and_certify.sh",
    "environments/gluonts-latest/p6_bootstrap_and_certify.sh",
    "src/loto/adapters/gluonts/p6_contract.py",
    "src/loto/adapters/gluonts/p6_registry.py",
    "src/loto/adapters/gluonts/p7_audit.py",
    "src/loto/adapters/gluonts/p7_cli.py",
    "src/loto/adapters/gluonts/p7_contract.py",
    "src/loto/adapters/gluonts/p7b_contract.py",
)

class SupervisorError(RuntimeError):
    pass


class ResumeIdentityError(SupervisorError):
    pass


@dataclass
class CommandResult:
    state: str
    return_code: int | None
    process_id: int | None
    process_group_id: int | None
    started_at_utc: str
    ended_at_utc: str
    errors: list[str]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_json(payload: Any) -> str:
    return sha256_bytes(canonical_json_bytes(payload))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_write_json(path: Path, payload: Any) -> str:
    content = canonical_json_bytes(payload)
    atomic_write(path, content)
    return sha256_bytes(content)


def atomic_write_text(path: Path, value: str) -> None:
    atomic_write(path, value.encode("utf-8"))


def command_sha256(command: list[str], environment: dict[str, str]) -> str:
    return sha256_json({"command": command, "environment": environment})


def git_output(repo_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


def collect_source_identity(repo_root: Path) -> dict[str, Any]:
    source_sha256: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = repo_root / relative
        if not path.is_file():
            raise SupervisorError(f"required source file is missing: {relative}")
        source_sha256[relative] = sha256_file(path)
    dirty = bool(git_output(repo_root, "status", "--porcelain", "--untracked-files=no"))
    return {
        "repository_root": str(repo_root),
        "branch": git_output(repo_root, "rev-parse", "--abbrev-ref", "HEAD"),
        "commit_sha": git_output(repo_root, "rev-parse", "HEAD"),
        "tracked_worktree_dirty": dirty,
        "source_sha256": source_sha256,
    }


def stage_template(stage: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "state": "PENDING",
        "attempt": 1,
        "command": [],
        "environment": {},
        "command_sha256": None,
        "started_at_utc": None,
        "ended_at_utc": None,
        "process_id": None,
        "process_group_id": None,
        "return_code": None,
        "timeout_seconds": None,
        "stdout_path": None,
        "stderr_path": None,
        "return_code_path": None,
        "artifact_root": None,
        "output_identity_sha256": None,
        "errors": [],
    }


def new_journal(
    run_id: str,
    output: Path,
    source_identity: dict[str, Any],
) -> dict[str, Any]:
    now = utc_now()
    return {
        "schema_version": 1,
        "phase": "P7B_TARGET_MACHINE_SUPERVISION",
        "run_id": run_id,
        "output_directory": str(output),
        "started_at_utc": now,
        "updated_at_utc": now,
        "execution_state": "RUNNING",
        "resume_count": 0,
        "source_identity": source_identity,
        "stages": {stage: stage_template(stage) for stage in STAGES},
        "errors": [],
    }


def write_journal(path: Path, journal: dict[str, Any]) -> str:
    journal["updated_at_utc"] = utc_now()
    return atomic_write_json(path, journal)


def relative_to_output(path: Path, output: Path) -> str:
    return path.resolve().relative_to(output.resolve()).as_posix()


def output_identity(
    output: Path,
    stdout_path: Path,
    stderr_path: Path,
    return_code_path: Path,
    artifact_root: Path | None,
) -> str:
    identities: dict[str, str] = {}
    for path in (stdout_path, stderr_path, return_code_path):
        if not path.is_file():
            raise ResumeIdentityError(f"completed stage output is missing: {path}")
        identities[relative_to_output(path, output)] = sha256_file(path)
    if artifact_root is not None:
        checksum_candidates = (
            artifact_root / "P6_SHA256SUMS",
            artifact_root / "P7_SHA256SUMS",
        )
        checksum = next((path for path in checksum_candidates if path.is_file()), None)
        if checksum is not None:
            identities[relative_to_output(checksum, output)] = sha256_file(checksum)
        elif artifact_root.exists():
            files = [path for path in sorted(artifact_root.rglob("*")) if path.is_file()]
            identities[relative_to_output(artifact_root, output)] = sha256_json(
                [
                    {
                        "path": path.relative_to(artifact_root).as_posix(),
                        "size": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                    for path in files
                ]
            )
    return sha256_json(identities)


def validate_completed_stage(output: Path, record: dict[str, Any]) -> None:
    stdout_path = output / record["stdout_path"]
    stderr_path = output / record["stderr_path"]
    return_code_path = output / record["return_code_path"]
    artifact_root = output / record["artifact_root"] if record["artifact_root"] else None
    observed = output_identity(
        output,
        stdout_path,
        stderr_path,
        return_code_path,
        artifact_root,
    )
    if observed != record["output_identity_sha256"]:
        raise ResumeIdentityError(
            f"completed stage output identity changed: {record['stage']}"
        )


def archive_interrupted_stage(output: Path, record: dict[str, Any]) -> None:
    history = output / "history"
    history.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    attempt = int(record["attempt"])
    destination = history / f"{record['stage']}-attempt-{attempt}-{stamp}"
    destination.mkdir()
    for field in ("stdout_path", "stderr_path", "return_code_path", "artifact_root"):
        relative = record.get(field)
        if not relative:
            continue
        source = output / relative
        if source.exists():
            shutil.move(str(source), str(destination / source.name))

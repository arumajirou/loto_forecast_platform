from __future__ import annotations

import os
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import (
    ResumeIdentityError,
    SupervisorError,
    archive_interrupted_stage,
    atomic_write_json,
    atomic_write_text,
    command_sha256,
    relative_to_output,
    sha256_file,
    sha256_json,
    stage_template,
    utc_now,
    validate_completed_stage,
    write_journal,
    output_identity,
)
from .process import execute_command

def verify_checksum_file(root: Path, checksum_name: str) -> None:
    checksum = root / checksum_name
    if not checksum.is_file():
        raise ResumeIdentityError(f"missing checksum file: {checksum}")
    expected_paths: set[str] = set()
    for line in checksum.read_text("utf-8").splitlines():
        digest, relative = line.split(maxsplit=1)
        relative = relative.strip()
        path = (root / relative).resolve()
        if root.resolve() not in path.parents and path != root.resolve():
            raise ResumeIdentityError("checksum path escapes execution root")
        if not path.is_file() or sha256_file(path) != digest:
            raise ResumeIdentityError(f"checksum verification failed: {relative}")
        expected_paths.add(path.relative_to(root.resolve()).as_posix())
    observed_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path.name not in {checksum_name, ".p7b.lock"}
    }
    if observed_paths != expected_paths:
        raise ResumeIdentityError("execution checksum inventory mismatch")


def stage_paths(output: Path, stage: str) -> tuple[Path, Path, Path, Path | None]:
    stdout_path = output / f"{stage}.stdout.log"
    stderr_path = output / f"{stage}.stderr.log"
    return_code_path = output / f"{stage}.rc"
    artifact_root = {
        "compat_bootstrap": output / "compat",
        "latest_bootstrap": output / "latest",
        "audit": output / "audit",
    }.get(stage)
    return stdout_path, stderr_path, return_code_path, artifact_root


def run_stage(
    output: Path,
    journal_path: Path,
    journal: dict[str, Any],
    stage: str,
    command: list[str],
    environment: dict[str, str],
    timeout_seconds: int,
    interrupted: threading.Event,
) -> int:
    record = journal["stages"][stage]
    if record["state"] == "COMPLETED":
        validate_completed_stage(output, record)
        return int(record["return_code"])
    if record["state"] in {"RUNNING", "TIMED_OUT", "INTERRUPTED", "FAILED_TO_START"}:
        archive_interrupted_stage(output, record)
        record = stage_template(stage)
        record["attempt"] = int(journal["stages"][stage]["attempt"]) + 1
        journal["stages"][stage] = record
    stdout_path, stderr_path, return_code_path, artifact_root = stage_paths(output, stage)
    record.update(
        {
            "command": command,
            "environment": environment,
            "command_sha256": command_sha256(command, environment),
            "timeout_seconds": timeout_seconds,
            "stdout_path": relative_to_output(stdout_path, output),
            "stderr_path": relative_to_output(stderr_path, output),
            "return_code_path": relative_to_output(return_code_path, output),
            "artifact_root": (
                relative_to_output(artifact_root, output) if artifact_root is not None else None
            ),
        }
    )
    write_journal(journal_path, journal)

    def on_started(pid: int, pgid: int, started: str) -> None:
        record.update(
            {
                "state": "RUNNING",
                "started_at_utc": started,
                "process_id": pid,
                "process_group_id": pgid,
            }
        )
        write_journal(journal_path, journal)

    result = execute_command(
        command,
        environment,
        timeout_seconds,
        stdout_path,
        stderr_path,
        on_started,
        interrupted,
    )
    persisted_return_code = result.return_code if result.return_code is not None else 127
    atomic_write_text(return_code_path, f"{persisted_return_code}\n")
    record.update(
        {
            "state": result.state,
            "started_at_utc": result.started_at_utc,
            "ended_at_utc": result.ended_at_utc,
            "process_id": result.process_id,
            "process_group_id": result.process_group_id,
            "return_code": result.return_code,
            "errors": result.errors,
        }
    )
    try:
        record["output_identity_sha256"] = output_identity(
            output,
            stdout_path,
            stderr_path,
            return_code_path,
            artifact_root,
        )
    except Exception as exc:
        record["errors"].append(f"output identity failed: {type(exc).__name__}: {exc}")
        if record["state"] == "COMPLETED":
            record["state"] = "FAILED_TO_START"
    write_journal(journal_path, journal)
    return result.return_code if result.return_code is not None else 127


def choose_audit_python(repo_root: Path) -> str:
    candidates = (
        repo_root / "environments/gluonts-compat/.venv/bin/python",
        repo_root / "environments/gluonts-latest/.venv/bin/python",
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            completed = subprocess.run(
                [str(candidate), "-c", "import pydantic"],
                capture_output=True,
                timeout=30,
                check=False,
            )
            if completed.returncode == 0:
                return str(candidate)
    python3 = shutil.which("python3")
    if python3 is not None:
        completed = subprocess.run(
            [python3, "-c", "import pydantic"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        if completed.returncode == 0:
            return python3
    raise SupervisorError("no Python interpreter with Pydantic is available for P7 audit")


def write_checksum_inventory(output: Path, checksum_name: str) -> str:
    checksum_path = output / checksum_name
    excluded = {
        checksum_name,
        "P7B_EXECUTION_SHA256SUMS",
        "P7B_PARTIAL_SHA256SUMS",
        ".p7b.lock",
    }
    lines = []
    for path in sorted(output.rglob("*")):
        if not path.is_file() or path.name in excluded:
            continue
        lines.append(f"{sha256_file(path)}  {path.relative_to(output).as_posix()}")
    atomic_write_text(checksum_path, "\n".join(lines) + "\n")
    return sha256_file(checksum_path)


def write_execution_checksums(output: Path) -> str:
    return write_checksum_inventory(output, "P7B_EXECUTION_SHA256SUMS")


def write_partial_checksums(output: Path) -> str:
    return write_checksum_inventory(output, "P7B_PARTIAL_SHA256SUMS")


def archive_partial_resume_state(output: Path, resume_number: int) -> None:
    partial = output / "P7B_PARTIAL_SHA256SUMS"
    if not partial.is_file():
        return
    verify_checksum_file(output, partial.name)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = output / "history" / f"resume-{resume_number}-{stamp}"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output / "p7b_execution_journal.json", destination / "journal.json")
    shutil.move(str(partial), str(destination / partial.name))


def finalize_execution(
    output: Path,
    journal_path: Path,
    journal: dict[str, Any],
    audit_return_code: int | None,
) -> None:
    record = journal["stages"]["finalize"]
    started = utc_now()
    record.update(
        {
            "state": "RUNNING",
            "started_at_utc": started,
            "process_id": os.getpid(),
            "process_group_id": os.getpgrp(),
        }
    )
    write_journal(journal_path, journal)
    stage_commands = {
        stage: journal["stages"][stage]["command_sha256"]
        for stage in ("compat_bootstrap", "latest_bootstrap", "audit")
    }
    stage_outputs = {
        stage: journal["stages"][stage]["output_identity_sha256"]
        for stage in ("compat_bootstrap", "latest_bootstrap", "audit")
        if journal["stages"][stage]["output_identity_sha256"] is not None
    }
    record.update(
        {
            "state": "COMPLETED",
            "ended_at_utc": utc_now(),
            "return_code": 0,
            "output_identity_sha256": sha256_json(stage_outputs),
        }
    )
    journal["execution_state"] = "COMPLETED"
    write_journal(journal_path, journal)
    journal_sha = sha256_file(journal_path)
    manifest = {
        "schema_version": 1,
        "phase": "P7B_TARGET_MACHINE_SUPERVISION",
        "run_id": journal["run_id"],
        "commit_sha": journal["source_identity"]["commit_sha"],
        "journal_sha256": journal_sha,
        "stage_command_sha256": stage_commands,
        "stage_output_identity_sha256": stage_outputs,
        "audit_return_code": audit_return_code,
        "finalized_at_utc": utc_now(),
    }
    atomic_write_json(output / "p7b_execution_manifest.json", manifest)
    atomic_write_text(
        output / "P7B_EXECUTION_COMPLETE",
        f"RUN_ID={journal['run_id']}\nCOMMIT_SHA={manifest['commit_sha']}\n",
    )
    write_execution_checksums(output)



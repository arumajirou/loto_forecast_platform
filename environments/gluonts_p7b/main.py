from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import signal
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from .common import (
    ResumeIdentityError,
    SupervisorError,
    atomic_write_json,
    atomic_write_text,
    collect_source_identity,
    new_journal,
    sha256_file,
    utc_now,
    write_journal,
)
from .process import GpuMonitor
from .stages import (
    archive_partial_resume_state,
    choose_audit_python,
    finalize_execution,
    run_stage,
    verify_checksum_file,
    write_partial_checksums,
)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Supervise resumable GluonTS P7 execution")
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--compat-timeout-seconds", type=int, default=14400)
    parser.add_argument("--latest-timeout-seconds", type=int, default=14400)
    parser.add_argument("--audit-timeout-seconds", type=int, default=1800)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = (args.repo_root or Path(__file__).resolve().parents[2]).resolve()
    run_id = args.run_id or f"gluonts-p7b-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    output = (args.output or repo_root / "artifacts/gluonts-p7b" / run_id).resolve()
    if output.exists() and any(output.iterdir()) and not args.resume:
        raise SupervisorError(f"output directory is not empty; use --resume: {output}")
    output.mkdir(parents=True, exist_ok=True)
    lock_path = output / ".p7b.lock"
    lock_handle = lock_path.open("a+")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise SupervisorError(f"another P7B execution owns {output}") from exc
    lock_handle.seek(0)
    lock_handle.truncate()
    lock_handle.write(f"pid={os.getpid()}\n")
    lock_handle.flush()

    journal_path = output / "p7b_execution_journal.json"
    source_identity = collect_source_identity(repo_root)
    if source_identity["tracked_worktree_dirty"]:
        raise SupervisorError("tracked worktree changes are not allowed for formal P7B execution")
    if args.resume:
        if not journal_path.is_file():
            raise SupervisorError("--resume requires p7b_execution_journal.json")
        journal = json.loads(journal_path.read_text("utf-8"))
        if journal["execution_state"] == "COMPLETED":
            verify_checksum_file(output, "P7B_EXECUTION_SHA256SUMS")
            audit_rc = journal["stages"]["audit"]["return_code"]
            print(f"P7B_RUN_ID={journal['run_id']}")
            print(f"P7B_ARTIFACT_DIR={output}")
            print(f"P7B_AUDIT_RC={audit_rc}")
            return int(audit_rc or 0)
        if journal["source_identity"] != source_identity:
            raise ResumeIdentityError("repository source identity changed since execution start")
        next_resume = int(journal["resume_count"]) + 1
        archive_partial_resume_state(output, next_resume)
        for record in journal["stages"].values():
            if (
                record["state"] == "COMPLETED"
                and record["stage"] not in {"preflight", "finalize"}
            ):
                validate_completed_stage(output, record)
        journal["resume_count"] = next_resume
        journal["execution_state"] = "RUNNING"
        journal["errors"] = []
        write_journal(journal_path, journal)
        run_id = journal["run_id"]
    else:
        journal = new_journal(run_id, output, source_identity)
        atomic_write_text(output / "RUN_ID", f"{run_id}\n")
        write_journal(journal_path, journal)

    preflight = journal["stages"]["preflight"]
    if preflight["state"] != "COMPLETED":
        started = utc_now()
        preflight_path = output / "p7b_preflight.json"
        payload = {
            "schema_version": 1,
            "run_id": run_id,
            "source_identity": source_identity,
            "commands": {
                name: shutil.which(name)
                for name in ("bash", "git", "uv", "sha256sum", "python3")
            },
            "disk_free_bytes": shutil.disk_usage(output).free,
            "nvidia_smi": shutil.which("nvidia-smi"),
            "timestamp_utc": started,
        }
        required_commands = ("bash", "git", "uv", "sha256sum")
        missing = [
            name
            for name in required_commands
            if payload["commands"][name] is None
        ]
        atomic_write_json(preflight_path, payload)
        preflight.update(
            {
                "state": "COMPLETED" if not missing else "FAILED_TO_START",
                "started_at_utc": started,
                "ended_at_utc": utc_now(),
                "process_id": os.getpid(),
                "process_group_id": os.getpgrp(),
                "return_code": 0 if not missing else 3,
                "artifact_root": None,
                "output_identity_sha256": sha256_file(preflight_path) if not missing else None,
                "errors": [] if not missing else [f"missing commands: {missing}"],
            }
        )
        write_journal(journal_path, journal)
        if missing:
            journal["execution_state"] = "BLOCKED"
            journal["errors"] = preflight["errors"]
            write_journal(journal_path, journal)
            write_partial_checksums(output)
            return 3

    interrupted = threading.Event()

    def handle_signal(signum: int, _frame: object) -> None:
        interrupted.set()
        journal["errors"] = [f"received signal {signum}"]

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    monitor = GpuMonitor(output / "gpu_process_monitor.jsonl")
    monitor.start()
    try:
        compat_rc = run_stage(
            output,
            journal_path,
            journal,
            "compat_bootstrap",
            [
                "bash",
                str(repo_root / "environments/gluonts-compat/p6_bootstrap_and_certify.sh"),
                str(output / "compat"),
            ],
            {"RUN_ID": f"{run_id}-compat"},
            args.compat_timeout_seconds,
            interrupted,
        )
        if interrupted.is_set():
            journal["execution_state"] = "INTERRUPTED"
            journal["errors"] = ["execution interrupted during compatibility lane"]
            write_journal(journal_path, journal)
            monitor.stop()
            write_partial_checksums(output)
            return 130
        latest_rc = run_stage(
            output,
            journal_path,
            journal,
            "latest_bootstrap",
            [
                "bash",
                str(repo_root / "environments/gluonts-latest/p6_bootstrap_and_certify.sh"),
                str(output / "latest"),
            ],
            {"RUN_ID": f"{run_id}-latest"},
            args.latest_timeout_seconds,
            interrupted,
        )
        if interrupted.is_set():
            journal["execution_state"] = "INTERRUPTED"
            journal["errors"] = ["execution interrupted during latest lane"]
            write_journal(journal_path, journal)
            monitor.stop()
            write_partial_checksums(output)
            return 130
        audit_python = choose_audit_python(repo_root)
        audit_rc = run_stage(
            output,
            journal_path,
            journal,
            "audit",
            [
                audit_python,
                "-m",
                "loto.adapters.gluonts.p7_cli",
                "--run-id",
                run_id,
                "--repo-root",
                str(repo_root),
                "--compat-artifact-root",
                str(output / "compat"),
                "--latest-artifact-root",
                str(output / "latest"),
                "--compat-return-code",
                str(compat_rc),
                "--latest-return-code",
                str(latest_rc),
                "--output-dir",
                str(output / "audit"),
            ],
            {"PYTHONPATH": str(repo_root / "src")},
            args.audit_timeout_seconds,
            interrupted,
        )
        if interrupted.is_set():
            journal["execution_state"] = "INTERRUPTED"
            journal["errors"] = ["execution interrupted during P7 audit"]
            write_journal(journal_path, journal)
            monitor.stop()
            write_partial_checksums(output)
            return 130
    finally:
        monitor.stop()

    if journal["stages"]["audit"]["state"] != "COMPLETED":
        journal["execution_state"] = "BLOCKED"
        journal["errors"] = journal["stages"]["audit"]["errors"] or [
            "P7 audit did not complete"
        ]
        write_journal(journal_path, journal)
        write_partial_checksums(output)
        return 124 if journal["stages"]["audit"]["state"] == "TIMED_OUT" else 3

    finalize_execution(output, journal_path, journal, audit_rc)
    audit_path = output / "audit/p7_target_machine_audit.json"
    print(audit_path.read_text("utf-8") if audit_path.is_file() else "")
    print(f"P7B_RUN_ID={run_id}")
    print(f"P7B_ARTIFACT_DIR={output}")
    print(f"P7B_COMPAT_RC={compat_rc}")
    print(f"P7B_LATEST_RC={latest_rc}")
    print(f"P7B_AUDIT_RC={audit_rc}")
    return audit_rc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SupervisorError as exc:
        print(f"P7B_BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc
    except Exception as exc:
        print(f"P7B_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc

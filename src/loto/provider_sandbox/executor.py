"""Bounded process runner for already-built argv plans."""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Mapping
from typing import BinaryIO

from .canonical import sha256_canonical
from .contracts import ProcessOutcome, SandboxArgvPlan, SandboxProcessResult


def _result(**values: object) -> SandboxProcessResult:
    payload = {"schema_version": "1.0.0", **values}
    return SandboxProcessResult(result_sha256=sha256_canonical(payload), **payload)


def _hash_file(handle: BinaryIO) -> tuple[str, int]:
    handle.flush()
    handle.seek(0)
    digest = hashlib.sha256()
    size = 0
    while chunk := handle.read(1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()


class SandboxProcessRunner:
    """Execute a validated argv plan without shell interpretation."""

    def run(
        self,
        plan: SandboxArgvPlan,
        *,
        timeout_seconds: float,
        output_limit_bytes: int,
        environment: Mapping[str, str] | None = None,
    ) -> SandboxProcessResult:
        started = time.monotonic_ns()
        process: subprocess.Popen[bytes] | None = None
        timed_out = False
        output_exceeded = False
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            try:
                process = subprocess.Popen(
                    list(plan.argv),
                    shell=False,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    env=dict(environment or {}),
                    close_fds=True,
                    start_new_session=True,
                )
                deadline = time.monotonic() + timeout_seconds
                while process.poll() is None:
                    output_size = (
                        os.fstat(stdout_file.fileno()).st_size
                        + os.fstat(stderr_file.fileno()).st_size
                    )
                    if output_size > output_limit_bytes:
                        output_exceeded = True
                        _kill_process_group(process)
                        break
                    if time.monotonic() >= deadline:
                        timed_out = True
                        _kill_process_group(process)
                        break
                    time.sleep(0.01)
                process.wait()
            except (OSError, ValueError):
                elapsed = max(0, (time.monotonic_ns() - started) // 1_000_000)
                empty_hash = hashlib.sha256(b"").hexdigest()
                return _result(
                    outcome=ProcessOutcome.LAUNCH_FAILED,
                    pid=None,
                    exit_code=None,
                    timed_out=False,
                    duration_ms=elapsed,
                    stdout_sha256=empty_hash,
                    stdout_size_bytes=0,
                    stderr_sha256=empty_hash,
                    stderr_size_bytes=0,
                    error_code="launch-failed",
                )
            stdout_hash, stdout_size = _hash_file(stdout_file)
            stderr_hash, stderr_size = _hash_file(stderr_file)
        elapsed = max(0, (time.monotonic_ns() - started) // 1_000_000)
        if timed_out:
            outcome = ProcessOutcome.TIMED_OUT
            error_code = "wall-timeout"
        elif output_exceeded or stdout_size + stderr_size > output_limit_bytes:
            outcome = ProcessOutcome.OUTPUT_LIMIT_EXCEEDED
            error_code = "output-limit-exceeded"
        elif process.returncode != 0:
            outcome = ProcessOutcome.NONZERO_EXIT
            error_code = "nonzero-exit"
        else:
            outcome = ProcessOutcome.SUCCEEDED
            error_code = None
        return _result(
            outcome=outcome,
            pid=process.pid,
            exit_code=process.returncode,
            timed_out=timed_out,
            duration_ms=elapsed,
            stdout_sha256=stdout_hash,
            stdout_size_bytes=stdout_size,
            stderr_sha256=stderr_hash,
            stderr_size_bytes=stderr_size,
            error_code=error_code,
        )

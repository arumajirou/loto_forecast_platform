"""Bounded subprocess execution with an injectable executor boundary."""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .contracts import CommandSpec, ProcessExecution


class ExecutionError(RuntimeError):
    pass


class Executor(Protocol):
    def execute(self, spec: CommandSpec, *, run_label: str) -> ProcessExecution: ...


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SubprocessExecutor:
    """Real executor. Provider-specific command construction remains outside the SDK."""

    def __init__(self, *, base_environment: Mapping[str, str] | None = None) -> None:
        self._base_environment = dict(base_environment or os.environ)

    def execute(self, spec: CommandSpec, *, run_label: str) -> ProcessExecution:
        started = datetime.now(UTC)
        environment = dict(self._base_environment)
        environment.update(spec.environment)
        try:
            completed = subprocess.run(
                spec.argv,
                cwd=Path(spec.cwd),
                env=environment,
                capture_output=True,
                text=True,
                timeout=spec.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            finished = datetime.now(UTC)
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return ProcessExecution(
                run_label=run_label,
                process_pid=None,
                started_at_utc=started,
                finished_at_utc=finished,
                exit_code=None,
                timed_out=True,
                stdout_sha256=_sha256_text(stdout),
                stderr_sha256=_sha256_text(stderr),
                response_sha256=None,
            )
        finished = datetime.now(UTC)
        return ProcessExecution(
            run_label=run_label,
            process_pid=None,
            started_at_utc=started,
            finished_at_utc=finished,
            exit_code=completed.returncode,
            timed_out=False,
            stdout_sha256=_sha256_text(completed.stdout),
            stderr_sha256=_sha256_text(completed.stderr),
            response_sha256=None,
        )

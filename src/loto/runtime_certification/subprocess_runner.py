"""Bounded subprocess execution with an injectable executor boundary."""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import threading
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Protocol

from .contracts import (
    CommandSpec,
    ProcessExecution,
    contains_control_characters,
    environment_name_is_dangerous,
    environment_name_is_sensitive,
)
from .device_evidence import read_process_identity_sha256


class ExecutionError(RuntimeError):
    pass


class Executor(Protocol):
    def execute(self, spec: CommandSpec, *, run_label: str) -> ProcessExecution: ...


_DEFAULT_MAX_STREAM_BYTES = 16 * 1024 * 1024
_INHERITED_ENVIRONMENT_KEYS = frozenset(
    {
        "COMSPEC",
        "CUDA_HOME",
        "CUDA_PATH",
        "CUDA_VISIBLE_DEVICES",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LD_LIBRARY_PATH",
        "NVIDIA_VISIBLE_DEVICES",
        "OMP_NUM_THREADS",
        "PATH",
        "PATHEXT",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "VIRTUAL_ENV",
        "WINDIR",
    }
)


def _base_environment(
    source: Mapping[str, str],
    *,
    restrict_to_inherited_allowlist: bool,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, value in source.items():
        if restrict_to_inherited_allowlist and name.upper() not in _INHERITED_ENVIRONMENT_KEYS:
            continue
        if (
            not name
            or "=" in name
            or contains_control_characters(name)
            or contains_control_characters(value)
            or environment_name_is_sensitive(name)
            or environment_name_is_dangerous(name)
        ):
            continue
        result[name] = value
    return result


def _validated_cwd(value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise ExecutionError("provider cwd must be an absolute directory")
    current = Path(candidate.anchor)
    for component in candidate.parts[1:]:
        current = current / component
        if current.is_symlink():
            raise ExecutionError("provider cwd must not contain symlink components")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        raise ExecutionError("provider cwd is unavailable") from None
    if not resolved.is_dir():
        raise ExecutionError("provider cwd must be an existing directory")
    return resolved


def _hash_stream(
    stream: BinaryIO,
    *,
    limit: int,
    overflow: threading.Event,
    result: dict[str, str],
    key: str,
) -> None:
    digest = hashlib.sha256()
    total = 0
    try:
        while True:
            block = stream.read(64 * 1024)
            if not block:
                break
            total += len(block)
            digest.update(block)
            if total > limit:
                overflow.set()
    finally:
        result[key] = digest.hexdigest()


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        try:
            subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5.0,
            )
        except (OSError, subprocess.SubprocessError):
            process.kill()
    if process.poll() is None:
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


class SubprocessExecutor:
    """Real executor. Provider-specific command construction remains outside the SDK."""

    def __init__(
        self,
        *,
        base_environment: Mapping[str, str] | None = None,
        max_stream_bytes: int = _DEFAULT_MAX_STREAM_BYTES,
    ) -> None:
        if max_stream_bytes < 1:
            raise ValueError("max_stream_bytes must be positive")
        if base_environment is None:
            self._base_environment = _base_environment(
                os.environ,
                restrict_to_inherited_allowlist=True,
            )
        else:
            self._base_environment = _base_environment(
                base_environment,
                restrict_to_inherited_allowlist=False,
            )
        self._max_stream_bytes = max_stream_bytes

    def execute(self, spec: CommandSpec, *, run_label: str) -> ProcessExecution:
        cwd = _validated_cwd(spec.cwd)
        environment = dict(self._base_environment)
        environment.update(spec.environment)
        started = datetime.now(UTC)
        try:
            process = subprocess.Popen(
                spec.argv,
                cwd=cwd,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=os.name == "posix",
            )
        except (OSError, ValueError):
            raise ExecutionError("failed to start provider process") from None

        process_identity = read_process_identity_sha256(process.pid)
        assert process.stdout is not None
        assert process.stderr is not None
        overflow = threading.Event()
        digests: dict[str, str] = {}
        readers = [
            threading.Thread(
                target=_hash_stream,
                kwargs={
                    "stream": process.stdout,
                    "limit": self._max_stream_bytes,
                    "overflow": overflow,
                    "result": digests,
                    "key": "stdout",
                },
                name=f"runtime-certification-stdout-{process.pid}",
            ),
            threading.Thread(
                target=_hash_stream,
                kwargs={
                    "stream": process.stderr,
                    "limit": self._max_stream_bytes,
                    "overflow": overflow,
                    "result": digests,
                    "key": "stderr",
                },
                name=f"runtime-certification-stderr-{process.pid}",
            ),
        ]
        for reader in readers:
            reader.start()

        deadline = time.monotonic() + spec.timeout_seconds
        timed_out = False
        output_exceeded = False
        while process.poll() is None:
            if overflow.is_set():
                output_exceeded = True
                _terminate_process_tree(process)
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                _terminate_process_tree(process)
                break
            try:
                process.wait(timeout=min(remaining, 0.05))
            except subprocess.TimeoutExpired:
                continue

        # A provider must not leave descendants running after its direct process exits.
        _terminate_process_tree(process)
        for reader in readers:
            reader.join(timeout=5.0)
        if any(reader.is_alive() for reader in readers):
            raise ExecutionError("provider output reader did not terminate")
        if overflow.is_set():
            output_exceeded = True
        if output_exceeded:
            raise ExecutionError("provider output exceeded configured stream limit")

        finished = datetime.now(UTC)
        return ProcessExecution(
            run_label=run_label,
            process_pid=process.pid,
            process_identity_sha256=process_identity,
            started_at_utc=started,
            finished_at_utc=finished,
            exit_code=None if timed_out else process.returncode,
            timed_out=timed_out,
            stdout_sha256=digests["stdout"],
            stderr_sha256=digests["stderr"],
            response_sha256=None,
        )

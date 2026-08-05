from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .common import CommandResult, utc_now

class GpuMonitor:
    def __init__(self, path: Path, interval_seconds: float = 2.0) -> None:
        self.path = path
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.thread = threading.Thread(target=self._run, name="p7b-gpu-monitor", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=max(5.0, self.interval_seconds * 2))

    def _run(self) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            while not self.stop_event.is_set():
                payload: dict[str, Any] = {"timestamp_utc": utc_now(), "processes": []}
                if shutil.which("nvidia-smi") is None:
                    payload["available"] = False
                    payload["error"] = "nvidia-smi unavailable"
                else:
                    try:
                        completed = subprocess.run(
                            [
                                "nvidia-smi",
                                "--query-compute-apps=pid,process_name,used_gpu_memory",
                                "--format=csv,noheader,nounits",
                            ],
                            capture_output=True,
                            text=True,
                            timeout=10,
                            check=False,
                        )
                        payload["available"] = True
                        payload["return_code"] = completed.returncode
                        for line in completed.stdout.splitlines():
                            parts = [part.strip() for part in line.split(",", 2)]
                            if len(parts) == 3 and parts[0].isdigit():
                                payload["processes"].append(
                                    {
                                        "pid": int(parts[0]),
                                        "process_name": parts[1],
                                        "used_gpu_memory_mib": (
                                            int(parts[2]) if parts[2].isdigit() else None
                                        ),
                                    }
                                )
                        if completed.stderr.strip():
                            payload["stderr"] = completed.stderr.strip()
                    except Exception as exc:
                        payload["available"] = True
                        payload["error"] = f"{type(exc).__name__}: {exc}"
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
                handle.flush()
                self.stop_event.wait(self.interval_seconds)


def terminate_process_group(process: subprocess.Popen[bytes], grace_seconds: int = 10) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait(timeout=grace_seconds)


def execute_command(
    command: list[str],
    environment: dict[str, sts],
    timeout_seconds: int,
    stdout_path: Path,
    stderr_path: Path,
    on_started: Callable[[int, int, str], None],
    interrupted: threading.Event,
) -> CommandResult:
    started = utc_now()
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    process: subprocess.Popen[bytes] | None = None
    try:
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            process = subprocess.Popen(
                command,
                env={**os.environ, **environment},
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
            on_started(process.pid, process.pid, started)
            deadline = time.monotonic() + timeout_seconds
            while True:
                return_code = process.poll()
                if return_code is not None:
                    return CommandResult(
                        state="COMPLETED",
                        return_code=return_code,
                        process_id=process.pid,
                        process_group_id=process.pid,
                        started_at_utc=started,
                        ended_at_utc=utc_now(),
                        errors=[],
                    )
                if interrupted.is_set():
                    terminate_process_group(process)
                    return CommandResult(
                        state="INTERRUPTED",
                        return_code=process.returncode,
                        process_id=process.pid,
                        process_group_id=process.pid,
                        started_at_utc=started,
                        ended_at_utc=utc_now(),
                        errors=["execution interrupted by signal"],
                    )
                if time.monotonic() >= deadline:
                    terminate_process_group(process)
                    return CommandResult(
                        state="TIMED_OUT",
                        return_code=124,
                        process_id=process.pid,
                        process_group_id=process.pid,
                        started_at_utc=started,
                        ended_at_utc=utc_now(),
                        errors=[f"stage exceeded timeout of {timeout_seconds} seconds"],
                    )
                time.sleep(0.2)
    except Exception as exc:
        if process is not None and process.poll() is None:
            terminate_process_group(process)
        return CommandResult(
            state="FAILED_TO_START",
            return_code=None,
            process_id=process.pid if process is not None else None,
            process_group_id=process.pid if process is not None else None,
            started_at_utc=started,
            ended_at_utc=utc_now(),
            errors=[f"{type(exc).__name__}: {exc}"],
        )



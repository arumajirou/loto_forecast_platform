"""Deterministic exclusive-GPU state machine.

The supervisor intentionally contains no LLM routing logic. It drains an optional
external request gate, unloads the configured LLM runtime, verifies that the GPU is
actually free, executes exactly one forecast command, then restores the LLM.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from datetime import UTC, datetime
from typing import Any

from .adapters import ExternalGate, HttpRuntime, NvidiaSmiProbe
from .models import SupervisorConfig, SupervisorState


class ExclusiveGpuError(RuntimeError):
    """Base exception for exclusive GPU handoff failures."""


class QwenReloadedDuringForecast(ExclusiveGpuError):
    """Raised when a bypassing client causes the unloaded LLM to return."""


class ExclusiveGpuSupervisor:
    def __init__(self, config: SupervisorConfig) -> None:
        self.config = config
        self.runtime = HttpRuntime(config.qwen)
        self.gpu = NvidiaSmiProbe(config.gpu)
        self.gate = ExternalGate(config.gate) if config.gate is not None else None
        self.state = SupervisorState.IDLE
        self.events: list[dict[str, Any]] = []
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def _record(self, event: str, **payload: Any) -> None:
        row = {"at_utc": self._now(), "state": self.state, "event": event, **payload}
        self.events.append(row)
        with (self.config.output_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def _transition(self, state: SupervisorState) -> None:
        previous = self.state
        self.state = state
        self._record("transition", previous=previous, current=state)
        self._write_state()

    def _write_state(self) -> None:
        payload = {"state": self.state, "updated_at_utc": self._now()}
        target = self.config.output_dir / "state.json"
        temp = target.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        temp.replace(target)

    def _acquire_lock(self) -> int:
        self.config.lock_path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(self.config.lock_path, flags, 0o600)
        except FileExistsError as exc:
            raise ExclusiveGpuError(
                f"GPU exclusive lock already exists: {self.config.lock_path}"
            ) from exc
        os.write(fd, f"pid={os.getpid()}\nstarted_at_utc={self._now()}\n".encode())
        return fd

    def _release_lock(self, fd: int) -> None:
        os.close(fd)
        self.config.lock_path.unlink(missing_ok=True)

    @staticmethod
    def _terminate_process(proc: subprocess.Popen[str], grace_seconds: float) -> None:
        if proc.poll() is not None:
            return
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
        try:
            proc.wait(timeout=grace_seconds)
            return
        except subprocess.TimeoutExpired:
            pass
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        proc.wait(timeout=grace_seconds)

    def _run_forecast(self) -> int:
        env = os.environ.copy()
        env.update(self.config.forecast.env)
        env["CUDA_VISIBLE_DEVICES"] = str(self.config.gpu.index)
        stdout_path = self.config.output_dir / "forecast.stdout.log"
        stderr_path = self.config.output_dir / "forecast.stderr.log"
        with (
            stdout_path.open("w", encoding="utf-8") as stdout,
            stderr_path.open("w", encoding="utf-8") as stderr,
        ):
            proc = subprocess.Popen(
                self.config.forecast.command,
                cwd=self.config.forecast.cwd,
                env=env,
                stdout=stdout,
                stderr=stderr,
                text=True,
                start_new_session=os.name == "posix",
            )
            started = time.monotonic()
            self._record("forecast_started", pid=proc.pid, command=self.config.forecast.command)
            while True:
                return_code = proc.poll()
                if return_code is not None:
                    self._record("forecast_exited", return_code=return_code)
                    return return_code
                if self.config.monitor_qwen_during_forecast and self.runtime.running():
                    self._record("qwen_reappeared_during_forecast", forecast_pid=proc.pid)
                    self._terminate_process(proc, self.config.forecast.terminate_grace_seconds)
                    raise QwenReloadedDuringForecast(
                        "Qwen became reachable while forecast owned the GPU; "
                        "a gate bypass or background client likely reloaded it"
                    )
                timeout = self.config.forecast.timeout_seconds
                if timeout is not None and time.monotonic() - started > timeout:
                    self._record("forecast_timeout", timeout_seconds=timeout)
                    self._terminate_process(proc, self.config.forecast.terminate_grace_seconds)
                    raise ExclusiveGpuError(f"forecast command exceeded timeout={timeout}s")
                time.sleep(min(self.config.qwen.poll_interval_seconds, 1.0))

    def run(self) -> dict[str, Any]:
        lock_fd = self._acquire_lock()
        qwen_initially_running = False
        qwen_stopped = False
        qwen_restored = False
        gate_closed = False
        gate_reopened = False
        forecast_exit_code: int | None = None
        failure: str | None = None
        try:
            self._write_state()
            qwen_initially_running = self.runtime.running()
            self._record("preflight", qwen_initially_running=qwen_initially_running)

            if self.gate is not None:
                self._transition(SupervisorState.DRAINING)
                self.gate.drain_and_close()
                gate_closed = True
                self._record("gate_closed")

            if qwen_initially_running:
                self._transition(SupervisorState.QWEN_STOPPING)
                self.runtime.stop()
                self.runtime.wait_running(False)
                qwen_stopped = True
                self._record("qwen_stopped")

            self._transition(SupervisorState.GPU_FREE)
            before = self.gpu.wait_free()
            self._record("gpu_free_before_forecast", snapshot=before.__dict__)

            self._transition(SupervisorState.FORECAST_RUNNING)
            forecast_exit_code = self._run_forecast()
            if forecast_exit_code != 0:
                raise ExclusiveGpuError(
                    f"forecast command failed with exit code {forecast_exit_code}"
                )

            self._transition(SupervisorState.FORECAST_STOPPING)
            after = self.gpu.wait_free()
            self._record("gpu_free_after_forecast", snapshot=after.__dict__)
        except Exception as exc:
            failure = f"{type(exc).__name__}: {exc}"
            self._transition(SupervisorState.FAILED)
            self._record("failure", error=failure)
        finally:
            restore_required = (
                self.config.restore_qwen_if_initially_running
                and qwen_initially_running
                and qwen_stopped
            )
            if restore_required:
                try:
                    self._transition(SupervisorState.QWEN_RESTORING)
                    self.runtime.start()
                    self.runtime.wait_running(True)
                    qwen_restored = True
                    self._transition(SupervisorState.QWEN_READY)
                    self._record("qwen_restored")
                except Exception as exc:
                    restore_error = f"{type(exc).__name__}: {exc}"
                    failure = f"{failure}; restore={restore_error}" if failure else restore_error
                    self.state = SupervisorState.FAILED
                    self._write_state()
                    self._record("qwen_restore_failed", error=restore_error)

            if self.gate is not None and gate_closed and (not restore_required or qwen_restored):
                try:
                    self.gate.open()
                    gate_reopened = True
                    self._record("gate_reopened")
                except Exception as exc:
                    gate_error = f"{type(exc).__name__}: {exc}"
                    failure = f"{failure}; gate_open={gate_error}" if failure else gate_error
                    self.state = SupervisorState.FAILED
                    self._write_state()
                    self._record("gate_reopen_failed", error=gate_error)

            success = failure is None and forecast_exit_code == 0
            if success:
                self.state = SupervisorState.IDLE
                self._write_state()
            result = {
                "status": "PASS" if success else "FAILED",
                "state": self.state,
                "qwen_initially_running": qwen_initially_running,
                "qwen_stopped": qwen_stopped,
                "qwen_restored": qwen_restored,
                "gate_reopened": gate_reopened,
                "forecast_exit_code": forecast_exit_code,
                "failure": failure,
                "output_dir": str(self.config.output_dir),
                "finished_at_utc": self._now(),
            }
            (self.config.output_dir / "result.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
            self._release_lock(lock_fd)
        return result

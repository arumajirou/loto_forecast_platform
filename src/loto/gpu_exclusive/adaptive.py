"""Adaptive COEXIST-or-HANDOFF GPU supervisor.

COEXIST means simultaneous VRAM residency only. The external request gate must be
drained and CLOSED before the foundation forecast begins, so the resident LLM cannot
grow its KV cache or perform concurrent inference while the forecast owns execution.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from .models import GpuResidencyProfile, ResidencyDecision, SupervisorConfig, SupervisorState
from .residency import (
    ResidencyProfileError,
    decide_residency,
    load_profile_registry,
    select_exact_profile,
)
from .supervisor import ExclusiveGpuError, ExclusiveGpuSupervisor


class AdaptiveGpuError(ExclusiveGpuError):
    """Raised when adaptive residency safety or continuity checks fail."""


class LlmContinuityLost(AdaptiveGpuError):
    """Raised when the resident LLM disappears or changes identity during COEXIST."""


class AdaptiveGpuSupervisor(ExclusiveGpuSupervisor):
    """Mode-aware supervisor that preserves ExclusiveGpuSupervisor as HANDOFF fallback."""

    def __init__(self, config: SupervisorConfig) -> None:
        super().__init__(config)
        self._selected_profile: GpuResidencyProfile | None = None

    def _resolve_profile(self, gpu_snapshot: Any) -> GpuResidencyProfile | None:
        policy = self.config.residency
        if policy.resource_profile_path is None or policy.profile_selector is None:
            return None
        path = Path(policy.resource_profile_path)
        if not path.is_file():
            return None
        registry = load_profile_registry(path)
        return select_exact_profile(
            registry,
            selector=policy.profile_selector,
            gpu=gpu_snapshot,
        )

    def _verify_coexist_identity(
        self,
        *,
        alias: str,
        expected_pids: set[int],
        gpu_uuid: str,
    ) -> None:
        identity = self.runtime.identity_snapshot()
        if not identity.running or alias not in identity.body:
            raise LlmContinuityLost("resident LLM identity is no longer reachable/exact")
        if self.config.residency.require_llm_pid_stability_when_available and expected_pids:
            current_pids = {process.pid for process in self.gpu.processes(gpu_uuid=gpu_uuid)}
            missing = expected_pids - current_pids
            if missing:
                raise LlmContinuityLost(
                    f"resident LLM GPU PID continuity lost: missing={sorted(missing)}"
                )

    def _run_forecast_coexist(
        self,
        *,
        alias: str,
        llm_pids: set[int],
        gpu_uuid: str,
    ) -> int:
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
            self._record(
                "forecast_started_coexist",
                pid=proc.pid,
                command=self.config.forecast.command,
                llm_gpu_pids=sorted(llm_pids),
            )
            while True:
                return_code = proc.poll()
                if return_code is not None:
                    self._record("forecast_exited", return_code=return_code)
                    return return_code
                try:
                    self._verify_coexist_identity(
                        alias=alias,
                        expected_pids=llm_pids,
                        gpu_uuid=gpu_uuid,
                    )
                except Exception:
                    self._terminate_process(proc, self.config.forecast.terminate_grace_seconds)
                    raise
                timeout = self.config.forecast.timeout_seconds
                if timeout is not None and time.monotonic() - started > timeout:
                    self._record("forecast_timeout", timeout_seconds=timeout)
                    self._terminate_process(proc, self.config.forecast.terminate_grace_seconds)
                    raise AdaptiveGpuError(f"forecast command exceeded timeout={timeout}s")
                time.sleep(min(self.config.qwen.poll_interval_seconds, 1.0))

    def _run_forced_handoff_compat(self) -> dict[str, Any]:
        """Preserve the pre-adaptive HANDOFF implementation byte-for-behavior."""

        started = time.monotonic()
        result = super().run()
        result["gpu_residency"] = {
            "requested_mode": "handoff",
            "selected_mode": "handoff",
            "decision_reason": "operator_forced_handoff",
            "profile_id": None,
            "gpu_uuid": None,
            "gpu_total_mib": None,
            "gpu_used_before_mib": None,
            "gpu_free_before_mib": None,
            "foundation_peak_mib": None,
            "foundation_budget_mib": None,
            "safety_reserve_mib": None,
            "llm_gpu_pids_before": [],
            "foreign_gpu_pids_before": [],
            "llm_gpu_pids_after": [],
            "llm_continuity_verified": False,
            "qwen_stopped": result.get("qwen_stopped"),
            "qwen_restored": result.get("qwen_restored"),
            "fallback_triggered": False,
        }
        result["timings_ms"] = {
            "residency_decision_ms": 0.0,
            "gate_drain_ms": None,
            "llm_unload_ms": None,
            "llm_reload_ms": None,
            "foundation_load_ms": None,
            "forecast_inference_ms": None,
            "total_tool_latency_ms": (time.monotonic() - started) * 1000.0,
        }
        (self.config.output_dir / "result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        return result

    def run(self) -> dict[str, Any]:
        if self.config.residency.mode == "handoff":
            return self._run_forced_handoff_compat()

        lock_fd = self._acquire_lock()
        started_total = time.monotonic()
        qwen_initially_running = False
        qwen_stopped = False
        qwen_restored = False
        gate_closed = False
        gate_reopened = False
        llm_continuity_verified = False
        forecast_exit_code: int | None = None
        failure: str | None = None
        decision: ResidencyDecision | None = None
        llm_pids_before: set[int] = set()
        llm_pids_after: list[int] = []
        baseline: Any | None = None
        timings: dict[str, float | None] = {
            "residency_decision_ms": None,
            "gate_drain_ms": None,
            "llm_unload_ms": 0.0,
            "llm_reload_ms": 0.0,
            "foundation_load_ms": None,
            "forecast_inference_ms": None,
            "total_tool_latency_ms": None,
        }
        try:
            self._write_state()
            initial_identity = self.runtime.identity_snapshot()
            qwen_initially_running = initial_identity.running
            self._record(
                "preflight",
                qwen_initially_running=qwen_initially_running,
                runtime_body_sha256=initial_identity.body_sha256,
            )
            if self.config.require_qwen_initially_running and not qwen_initially_running:
                raise AdaptiveGpuError(
                    "selected Qwen runtime must be live before adaptive GPU execution"
                )

            if self.gate is not None:
                self._transition(SupervisorState.DRAINING)
                gate_started = time.monotonic()
                self.gate.drain_and_close()
                timings["gate_drain_ms"] = (time.monotonic() - gate_started) * 1000.0
                gate_closed = True
                self._record("gate_closed")

            self._transition(SupervisorState.RESIDENCY_DECIDING)
            decision_started = time.monotonic()
            baseline = self.gpu.snapshot()
            processes_before = self.gpu.processes(gpu_uuid=baseline.uuid)
            try:
                profile = self._resolve_profile(baseline)
            except ResidencyProfileError as exc:
                raise AdaptiveGpuError(str(exc)) from exc
            self._selected_profile = profile
            decision = decide_residency(
                self.config.residency,
                gpu=baseline,
                processes=processes_before,
                runtime=initial_identity,
                profile=profile,
            )
            timings["residency_decision_ms"] = (time.monotonic() - decision_started) * 1000.0
            llm_pids_before = set(decision.llm_gpu_pids_before)
            self._record("residency_decision", decision=decision.model_dump(mode="json"))

            if decision.selected_mode == "block":
                raise AdaptiveGpuError(
                    f"adaptive residency blocked execution: {decision.decision_reason}"
                )

            if decision.selected_mode == "handoff":
                if qwen_initially_running:
                    self._transition(SupervisorState.QWEN_STOPPING)
                    unload_started = time.monotonic()
                    self.runtime.stop()
                    self.runtime.wait_running(False)
                    timings["llm_unload_ms"] = (time.monotonic() - unload_started) * 1000.0
                    qwen_stopped = True
                    self._record("qwen_stopped")

                self._transition(SupervisorState.GPU_FREE)
                free_before = self.gpu.wait_free()
                self._record("gpu_free_before_forecast", snapshot=free_before.__dict__)

                self._transition(SupervisorState.FORECAST_RUNNING)
                forecast_started = time.monotonic()
                forecast_exit_code = self._run_forecast()
                timings["forecast_inference_ms"] = (
                    time.monotonic() - forecast_started
                ) * 1000.0
                if forecast_exit_code != 0:
                    raise AdaptiveGpuError(
                        f"forecast command failed with exit code {forecast_exit_code}"
                    )

                self._transition(SupervisorState.FORECAST_STOPPING)
                after = self.gpu.wait_free()
                self._record("gpu_free_after_forecast", snapshot=after.__dict__)
            else:
                if profile is None:
                    raise AdaptiveGpuError("COEXIST selected without an exact profile")
                self._transition(SupervisorState.COEXIST_READY)
                self._verify_coexist_identity(
                    alias=profile.llm.alias,
                    expected_pids=llm_pids_before,
                    gpu_uuid=baseline.uuid,
                )
                self._record(
                    "coexist_ready",
                    profile_id=profile.profile_id,
                    llm_gpu_pids=sorted(llm_pids_before),
                )

                self._transition(SupervisorState.FORECAST_RUNNING)
                forecast_started = time.monotonic()
                forecast_exit_code = self._run_forecast_coexist(
                    alias=profile.llm.alias,
                    llm_pids=llm_pids_before,
                    gpu_uuid=baseline.uuid,
                )
                timings["forecast_inference_ms"] = (
                    time.monotonic() - forecast_started
                ) * 1000.0
                if forecast_exit_code != 0:
                    raise AdaptiveGpuError(
                        f"forecast command failed with exit code {forecast_exit_code}"
                    )

                self._transition(SupervisorState.FORECAST_STOPPING)
                after = self.gpu.wait_for_baseline(
                    baseline=baseline,
                    baseline_pids=llm_pids_before,
                    tolerance_mib=self.config.residency.post_run_vram_tolerance_mib,
                )
                self._record("gpu_returned_to_coexist_baseline", snapshot=after.__dict__)

                self._transition(SupervisorState.LLM_CONTINUITY_CHECK)
                self._verify_coexist_identity(
                    alias=profile.llm.alias,
                    expected_pids=llm_pids_before,
                    gpu_uuid=baseline.uuid,
                )
                llm_pids_after = sorted(
                    process.pid
                    for process in self.gpu.processes(gpu_uuid=baseline.uuid)
                    if process.pid in llm_pids_before
                )
                llm_continuity_verified = set(llm_pids_after) == llm_pids_before
                if not llm_continuity_verified:
                    raise LlmContinuityLost("post-run LLM PID continuity verification failed")
                self._transition(SupervisorState.QWEN_READY)
                self._record("llm_continuity_verified", llm_gpu_pids_after=llm_pids_after)
        except Exception as exc:
            failure = f"{type(exc).__name__}: {exc}"
            self._transition(SupervisorState.FAILED)
            self._record("failure", error=failure)
        finally:
            selected_mode = decision.selected_mode if decision is not None else None
            restore_required = (
                selected_mode == "handoff"
                and self.config.restore_qwen_if_initially_running
                and qwen_initially_running
                and qwen_stopped
            )
            if restore_required:
                try:
                    self._transition(SupervisorState.QWEN_RESTORING)
                    reload_started = time.monotonic()
                    self.runtime.start()
                    self.runtime.wait_running(True)
                    timings["llm_reload_ms"] = (time.monotonic() - reload_started) * 1000.0
                    qwen_restored = True
                    self._transition(SupervisorState.QWEN_READY)
                    self._record("qwen_restored")
                except Exception as exc:
                    restore_error = f"{type(exc).__name__}: {exc}"
                    failure = f"{failure}; restore={restore_error}" if failure else restore_error
                    self.state = SupervisorState.FAILED
                    self._write_state()
                    self._record("qwen_restore_failed", error=restore_error)

            if (
                selected_mode == "coexist"
                and not llm_continuity_verified
                and baseline is not None
                and self._selected_profile is not None
            ):
                try:
                    self.gpu.wait_for_baseline(
                        baseline=baseline,
                        baseline_pids=llm_pids_before,
                        tolerance_mib=self.config.residency.post_run_vram_tolerance_mib,
                    )
                    self._verify_coexist_identity(
                        alias=self._selected_profile.llm.alias,
                        expected_pids=llm_pids_before,
                        gpu_uuid=baseline.uuid,
                    )
                    llm_continuity_verified = True
                    self._record("llm_continuity_recovered_after_forecast_failure")
                except Exception as exc:
                    continuity_error = f"{type(exc).__name__}: {exc}"
                    failure = (
                        f"{failure}; continuity={continuity_error}" if failure else continuity_error
                    )

            gate_safe = (
                selected_mode == "handoff" and (not restore_required or qwen_restored)
            ) or (selected_mode == "coexist" and llm_continuity_verified)
            if self.gate is not None and gate_closed and gate_safe:
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

            timings["total_tool_latency_ms"] = (time.monotonic() - started_total) * 1000.0
            residency_payload = (
                decision.model_dump(mode="json")
                if decision is not None
                else {
                    "requested_mode": self.config.residency.mode,
                    "selected_mode": "block",
                    "decision_reason": "decision_not_reached",
                    "fallback_triggered": False,
                }
            )
            residency_payload.update(
                {
                    "llm_gpu_pids_after": llm_pids_after,
                    "llm_continuity_verified": llm_continuity_verified,
                    "qwen_stopped": qwen_stopped,
                    "qwen_restored": qwen_restored,
                }
            )
            result = {
                "status": "PASS" if success else "FAILED",
                "state": self.state,
                "qwen_initially_running": qwen_initially_running,
                "qwen_stopped": qwen_stopped,
                "qwen_restored": qwen_restored,
                "gate_reopened": gate_reopened,
                "forecast_exit_code": forecast_exit_code,
                "failure": failure,
                "gpu_residency": residency_payload,
                "timings_ms": timings,
                "output_dir": str(self.config.output_dir),
                "finished_at_utc": self._now(),
            }
            (self.config.output_dir / "result.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
            self._release_lock(lock_fd)
        return result

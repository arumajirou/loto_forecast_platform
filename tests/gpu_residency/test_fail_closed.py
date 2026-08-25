from __future__ import annotations

import json
import sys
from pathlib import Path

from loto.gpu_exclusive.adapters import (
    AdapterError,
    GpuProcessSnapshot,
    GpuSnapshot,
    RuntimeIdentitySnapshot,
)
from loto.gpu_exclusive.adaptive import AdaptiveGpuSupervisor
from loto.gpu_exclusive.models import (
    ForecastJobConfig,
    GpuProbeConfig,
    GpuResidencyPolicy,
    HttpRuntimeConfig,
    ResidencyProfileSelector,
    SupervisorConfig,
)
from loto.gpu_exclusive.residency import decide_residency


class Gate:
    def __init__(self) -> None:
        self.closed = False
        self.opened = False

    def drain_and_close(self) -> None:
        self.closed = True

    def open(self) -> None:
        self.opened = True


class Runtime:
    def __init__(self, *, disappear_after: int | None = None) -> None:
        self.calls = 0
        self.disappear_after = disappear_after

    def identity_snapshot(self) -> RuntimeIdentitySnapshot:
        self.calls += 1
        running = self.disappear_after is None or self.calls < self.disappear_after
        return RuntimeIdentitySnapshot(
            running=running,
            body="qwen" if running else "",
            body_sha256="same" if running else "",
        )

    def running(self) -> bool:
        return self.identity_snapshot().running

    def start(self) -> None:
        raise AssertionError("COEXIST must not start LLM")

    def stop(self) -> None:
        raise AssertionError("COEXIST must not stop LLM")

    def wait_running(self, expected: bool) -> None:
        assert self.running() is expected


class Gpu:
    def __init__(self, *, lose_pid: bool = False, leak: bool = False) -> None:
        self.lose_pid = lose_pid
        self.leak = leak
        self.process_calls = 0
        self.baseline = GpuSnapshot(
            index=0,
            uuid="GPU-x",
            memory_used_mib=11000,
            memory_free_mib=5303,
            memory_total_mib=16303,
        )

    def snapshot(self) -> GpuSnapshot:
        return self.baseline

    def processes(self, *, gpu_uuid: str | None = None) -> list[GpuProcessSnapshot]:
        assert gpu_uuid in (None, "GPU-x")
        self.process_calls += 1
        if self.lose_pid and self.process_calls >= 2:
            return []
        return [
            GpuProcessSnapshot(
                gpu_uuid="GPU-x",
                pid=101,
                process_name="llama-server",
                used_memory_mib=11000,
            )
        ]

    def wait_for_baseline(
        self,
        *,
        baseline: GpuSnapshot,
        baseline_pids: set[int],
        tolerance_mib: int,
    ) -> GpuSnapshot:
        assert baseline_pids == {101}
        if self.leak:
            raise AdapterError("synthetic post-run VRAM leak")
        return baseline

    def wait_free(self) -> GpuSnapshot:
        raise AssertionError("COEXIST must not require an empty GPU")


def _selector() -> ResidencyProfileSelector:
    return ResidencyProfileSelector(
        llm_alias="qwen",
        llm_runtime="ik_llama",
        llm_context_length=65536,
        foundation_repo_id="Salesforce/moirai-2.0-R-small",
        foundation_revision="30f43ff08c8494f4943ae1521e9d4e94a0fbb389",
        runtime_lane="cuda13-experimental",
    )


def _profile(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": [
                    {
                        "profile_id": "p",
                        "certified": True,
                        "gpu": {"uuid": "GPU-x", "index": 0},
                        "llm": {
                            "alias": "qwen",
                            "runtime": "ik_llama",
                            "context_length": 65536,
                            "process_names": ["llama-server"],
                        },
                        "foundation": {
                            "repo_id": "Salesforce/moirai-2.0-R-small",
                            "revision": "30f43ff08c8494f4943ae1521e9d4e94a0fbb389",
                            "runtime_lane": "cuda13-experimental",
                        },
                        "evidence": {
                            "external_peak_vram_mib": 1000,
                            "sample_count": 3,
                            "certification_run_ids": ["1", "2", "3"],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _config(tmp_path: Path) -> SupervisorConfig:
    profile = tmp_path / "profiles.json"
    _profile(profile)
    return SupervisorConfig(
        qwen=HttpRuntimeConfig(
            running_url="http://127.0.0.1/running",
            running_contains="qwen",
            start_url="http://127.0.0.1/start",
            stop_url="http://127.0.0.1/stop",
            poll_interval_seconds=0.01,
        ),
        gpu=GpuProbeConfig(index=0, stable_samples=1),
        forecast=ForecastJobConfig(
            command=[sys.executable, "-c", "import time; time.sleep(0.1)"],
            cwd=tmp_path,
        ),
        output_dir=tmp_path / "out",
        lock_path=tmp_path / "lock",
        require_qwen_initially_running=True,
        residency=GpuResidencyPolicy(
            mode="auto",
            resource_profile_path=profile,
            profile_selector=_selector(),
            reserve_ratio=0.0,
            hard_reserve_mib=2048,
            foundation_peak_safety_factor=1.25,
        ),
    )


def _run(tmp_path: Path, *, runtime: Runtime, gpu: Gpu) -> tuple[dict, Gate]:
    supervisor = AdaptiveGpuSupervisor(_config(tmp_path))
    gate = Gate()
    supervisor.runtime = runtime  # type: ignore[assignment]
    supervisor.gpu = gpu  # type: ignore[assignment]
    supervisor.gate = gate  # type: ignore[assignment]
    return supervisor.run(), gate


def test_coexist_llm_disappearance_keeps_gate_closed(tmp_path: Path) -> None:
    result, gate = _run(tmp_path, runtime=Runtime(disappear_after=2), gpu=Gpu())
    assert result["status"] == "FAILED"
    assert "LlmContinuityLost" in str(result["failure"])
    assert gate.closed is True
    assert gate.opened is False


def test_coexist_pid_change_keeps_gate_closed(tmp_path: Path) -> None:
    result, gate = _run(tmp_path, runtime=Runtime(), gpu=Gpu(lose_pid=True))
    assert result["status"] == "FAILED"
    assert "PID continuity" in str(result["failure"])
    assert gate.opened is False


def test_coexist_post_run_vram_leak_keeps_gate_closed(tmp_path: Path) -> None:
    result, gate = _run(tmp_path, runtime=Runtime(), gpu=Gpu(leak=True))
    assert result["status"] == "FAILED"
    assert "VRAM leak" in str(result["failure"])
    assert gate.opened is False


def test_forced_coexist_with_foreign_gpu_process_blocks() -> None:
    policy = GpuResidencyPolicy(
        mode="coexist",
        profile_selector=_selector(),
        reserve_ratio=0.0,
    )
    from loto.gpu_exclusive.models import GpuResidencyProfile

    profile = GpuResidencyProfile.model_validate(
        {
            "profile_id": "p",
            "certified": True,
            "gpu": {"uuid": "GPU-x", "index": 0},
            "llm": {
                "alias": "qwen",
                "runtime": "ik_llama",
                "context_length": 65536,
                "process_names": ["llama-server"],
            },
            "foundation": {
                "repo_id": "Salesforce/moirai-2.0-R-small",
                "revision": "30f43ff08c8494f4943ae1521e9d4e94a0fbb389",
                "runtime_lane": "cuda13-experimental",
            },
            "evidence": {
                "external_peak_vram_mib": 100,
                "sample_count": 3,
                "certification_run_ids": ["1", "2", "3"],
            },
        }
    )
    decision = decide_residency(
        policy,
        gpu=Gpu().baseline,
        processes=[
            GpuProcessSnapshot("GPU-x", 101, "llama-server", 11000),
            GpuProcessSnapshot("GPU-x", 202, "foreign", 100),
        ],
        runtime=RuntimeIdentitySnapshot(True, "qwen", "same"),
        profile=profile,
    )
    assert decision.selected_mode == "block"
    assert decision.decision_reason == "foreign_gpu_process_present"

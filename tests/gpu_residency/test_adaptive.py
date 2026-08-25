from __future__ import annotations

import json
import sys
from pathlib import Path

from loto.gpu_exclusive.adapters import (
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


class FakeRuntime:
    def __init__(self) -> None:
        self.is_running = True
        self.stop_calls = 0
        self.start_calls = 0

    def identity_snapshot(self) -> RuntimeIdentitySnapshot:
        body = "qwen38-27b-ud-iq3xxs-mtp3" if self.is_running else ""
        return RuntimeIdentitySnapshot(
            running=self.is_running,
            body=body,
            body_sha256="same" if self.is_running else "",
        )

    def running(self) -> bool:
        return self.is_running

    def stop(self) -> None:
        self.stop_calls += 1
        self.is_running = False

    def start(self) -> None:
        self.start_calls += 1
        self.is_running = True

    def wait_running(self, expected: bool) -> None:
        assert self.is_running is expected


class FakeGpu:
    def __init__(self, *, free_mib: int = 5000) -> None:
        self.snapshot_value = GpuSnapshot(
            index=0,
            uuid="GPU-test",
            memory_used_mib=16303 - free_mib,
            memory_free_mib=free_mib,
            memory_total_mib=16303,
        )

    def snapshot(self) -> GpuSnapshot:
        return self.snapshot_value

    def processes(self, *, gpu_uuid: str | None = None) -> list[GpuProcessSnapshot]:
        assert gpu_uuid in (None, "GPU-test")
        return [
            GpuProcessSnapshot(
                gpu_uuid="GPU-test",
                pid=100,
                process_name="llama-server",
                used_memory_mib=11000,
            )
        ]

    def wait_free(self) -> GpuSnapshot:
        return GpuSnapshot(
            index=0,
            uuid="GPU-test",
            memory_used_mib=100,
            memory_free_mib=16203,
            memory_total_mib=16303,
        )

    def wait_for_baseline(
        self,
        *,
        baseline: GpuSnapshot,
        baseline_pids: set[int],
        tolerance_mib: int,
    ) -> GpuSnapshot:
        assert baseline_pids == {100}
        assert tolerance_mib == 256
        return baseline


class FakeGate:
    def __init__(self) -> None:
        self.closed = False
        self.opened = False

    def drain_and_close(self) -> None:
        self.closed = True

    def open(self) -> None:
        self.opened = True


def _selector() -> ResidencyProfileSelector:
    return ResidencyProfileSelector(
        llm_alias="qwen38-27b-ud-iq3xxs-mtp3",
        llm_runtime="ik_llama",
        llm_context_length=65536,
        foundation_repo_id="Salesforce/moirai-2.0-R-small",
        foundation_revision="30f43ff08c8494f4943ae1521e9d4e94a0fbb389",
        runtime_lane="cuda13-experimental",
    )


def _write_profile(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": [
                    {
                        "profile_id": "iq3xxs-moirai2-test",
                        "certified": True,
                        "gpu": {"uuid": "GPU-test", "index": 0},
                        "llm": {
                            "alias": "qwen38-27b-ud-iq3xxs-mtp3",
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
                            "external_peak_vram_mib": 2000,
                            "sample_count": 3,
                            "certification_run_ids": ["r1", "r2", "r3"],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _config(tmp_path: Path, policy: GpuResidencyPolicy) -> SupervisorConfig:
    return SupervisorConfig(
        qwen=HttpRuntimeConfig(
            running_url="http://127.0.0.1/running",
            running_contains="qwen38-27b-ud-iq3xxs-mtp3",
            start_url="http://127.0.0.1/start",
            stop_url="http://127.0.0.1/stop",
            poll_interval_seconds=0.01,
        ),
        gpu=GpuProbeConfig(index=0, stable_samples=1),
        forecast=ForecastJobConfig(
            command=[sys.executable, "-c", "print('ok')"],
            cwd=tmp_path,
        ),
        output_dir=tmp_path / "out",
        lock_path=tmp_path / "lock",
        require_qwen_initially_running=True,
        residency=policy,
    )


def test_forced_handoff_preserves_stop_restore_path(tmp_path: Path) -> None:
    supervisor = AdaptiveGpuSupervisor(_config(tmp_path, GpuResidencyPolicy(mode="handoff")))
    runtime = FakeRuntime()
    gate = FakeGate()
    supervisor.runtime = runtime  # type: ignore[assignment]
    supervisor.gpu = FakeGpu()  # type: ignore[assignment]
    supervisor.gate = gate  # type: ignore[assignment]

    result = supervisor.run()

    assert result["status"] == "PASS"
    assert result["gpu_residency"]["selected_mode"] == "handoff"
    assert runtime.stop_calls == 1
    assert runtime.start_calls == 1
    assert gate.closed is True
    assert gate.opened is True


def test_auto_coexist_never_stops_or_starts_llm(tmp_path: Path) -> None:
    profile_path = tmp_path / "profiles.json"
    _write_profile(profile_path)
    policy = GpuResidencyPolicy(
        mode="auto",
        resource_profile_path=profile_path,
        profile_selector=_selector(),
        hard_reserve_mib=2048,
        reserve_ratio=0.0,
        foundation_peak_safety_factor=1.25,
    )
    supervisor = AdaptiveGpuSupervisor(_config(tmp_path, policy))
    runtime = FakeRuntime()
    gate = FakeGate()
    supervisor.runtime = runtime  # type: ignore[assignment]
    supervisor.gpu = FakeGpu(free_mib=5000)  # type: ignore[assignment]
    supervisor.gate = gate  # type: ignore[assignment]

    result = supervisor.run()

    assert result["status"] == "PASS"
    assert result["gpu_residency"]["selected_mode"] == "coexist"
    assert result["gpu_residency"]["llm_continuity_verified"] is True
    assert result["qwen_stopped"] is False
    assert result["qwen_restored"] is False
    assert runtime.stop_calls == 0
    assert runtime.start_calls == 0
    assert gate.closed is True
    assert gate.opened is True


def test_auto_unknown_profile_falls_back_to_handoff(tmp_path: Path) -> None:
    policy = GpuResidencyPolicy(
        mode="auto",
        resource_profile_path=tmp_path / "missing.json",
        profile_selector=_selector(),
    )
    supervisor = AdaptiveGpuSupervisor(_config(tmp_path, policy))
    runtime = FakeRuntime()
    gate = FakeGate()
    supervisor.runtime = runtime  # type: ignore[assignment]
    supervisor.gpu = FakeGpu()  # type: ignore[assignment]
    supervisor.gate = gate  # type: ignore[assignment]

    result = supervisor.run()

    assert result["status"] == "PASS"
    assert result["gpu_residency"]["selected_mode"] == "handoff"
    assert result["gpu_residency"]["fallback_triggered"] is True
    assert runtime.stop_calls == 1
    assert runtime.start_calls == 1

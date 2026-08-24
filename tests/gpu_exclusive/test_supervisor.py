from __future__ import annotations

from pathlib import Path

import pytest

from loto.gpu_exclusive.models import (
    ForecastJobConfig,
    GpuProbeConfig,
    HttpRuntimeConfig,
    SupervisorConfig,
    SupervisorState,
)
from loto.gpu_exclusive.supervisor import ExclusiveGpuSupervisor


class FakeRuntime:
    def __init__(self, *, running: bool = True, reappear_during_forecast: bool = False) -> None:
        self.is_running = running
        self.reappear_during_forecast = reappear_during_forecast
        self.running_calls = 0

    def running(self) -> bool:
        self.running_calls += 1
        if self.reappear_during_forecast and self.running_calls >= 3:
            self.is_running = True
        return self.is_running

    def start(self) -> None:
        self.is_running = True

    def stop(self) -> None:
        self.is_running = False

    def wait_running(self, expected: bool) -> None:
        assert self.is_running is expected


class FakeGpu:
    class Snapshot:
        index = 0
        memory_used_mib = 100
        memory_total_mib = 16384

        @property
        def __dict__(self) -> dict[str, int]:
            return {
                "index": self.index,
                "memory_used_mib": self.memory_used_mib,
                "memory_total_mib": self.memory_total_mib,
            }

    def wait_free(self) -> Snapshot:
        return self.Snapshot()


class FakeGate:
    def __init__(self) -> None:
        self.closed = False
        self.opened = False

    def drain_and_close(self) -> None:
        self.closed = True

    def open(self) -> None:
        self.opened = True


def _config(tmp_path: Path, command: list[str]) -> SupervisorConfig:
    return SupervisorConfig(
        qwen=HttpRuntimeConfig(
            running_url="http://127.0.0.1:1/running",
            running_contains="qwen",
            start_url="http://127.0.0.1:1/load",
            stop_url="http://127.0.0.1:1/unload",
        ),
        gpu=GpuProbeConfig(max_memory_used_mib_when_free=1024),
        forecast=ForecastJobConfig(command=command, cwd=tmp_path),
        output_dir=tmp_path / "out",
        lock_path=tmp_path / "exclusive.lock",
    )


def test_success_restores_qwen_and_returns_to_idle(tmp_path: Path) -> None:
    config = _config(tmp_path, ["python", "-c", "print('forecast ok')"])
    supervisor = ExclusiveGpuSupervisor(config)
    runtime = FakeRuntime(running=True)
    gpu = FakeGpu()
    gate = FakeGate()
    supervisor.runtime = runtime  # type: ignore[assignment]
    supervisor.gpu = gpu  # type: ignore[assignment]
    supervisor.gate = gate  # type: ignore[assignment]

    result = supervisor.run()

    assert result["status"] == "PASS"
    assert result["qwen_stopped"] is True
    assert result["qwen_restored"] is True
    assert runtime.is_running is True
    assert gate.closed is True
    assert gate.opened is True
    assert supervisor.state is SupervisorState.IDLE
    assert (config.output_dir / "result.json").is_file()


def test_forecast_failure_still_restores_qwen(tmp_path: Path) -> None:
    config = _config(tmp_path, ["python", "-c", "raise SystemExit(7)"])
    supervisor = ExclusiveGpuSupervisor(config)
    runtime = FakeRuntime(running=True)
    supervisor.runtime = runtime  # type: ignore[assignment]
    supervisor.gpu = FakeGpu()  # type: ignore[assignment]

    result = supervisor.run()

    assert result["status"] == "FAILED"
    assert result["forecast_exit_code"] == 7
    assert result["qwen_restored"] is True
    assert runtime.is_running is True


def test_reappearing_qwen_is_fail_closed_and_restored(tmp_path: Path) -> None:
    config = _config(tmp_path, ["python", "-c", "import time; time.sleep(5)"])
    supervisor = ExclusiveGpuSupervisor(config)
    runtime = FakeRuntime(running=True, reappear_during_forecast=True)
    supervisor.runtime = runtime  # type: ignore[assignment]
    supervisor.gpu = FakeGpu()  # type: ignore[assignment]

    result = supervisor.run()

    assert result["status"] == "FAILED"
    assert "QwenReloadedDuringForecast" in str(result["failure"])
    assert runtime.is_running is True


def test_empty_forecast_command_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="forecast command must not be empty"):
        ForecastJobConfig(command=[], cwd=tmp_path)

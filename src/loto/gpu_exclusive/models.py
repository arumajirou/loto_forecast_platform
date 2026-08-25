"""Configuration and state models for exclusive GPU handoff."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SupervisorState(StrEnum):
    IDLE = "IDLE"
    DRAINING = "DRAINING"
    QWEN_STOPPING = "QWEN_STOPPING"
    GPU_FREE = "GPU_FREE"
    FORECAST_RUNNING = "FORECAST_RUNNING"
    FORECAST_STOPPING = "FORECAST_STOPPING"
    QWEN_RESTORING = "QWEN_RESTORING"
    QWEN_READY = "QWEN_READY"
    FAILED = "FAILED"


class HttpRuntimeConfig(BaseModel):
    """HTTP controls for one externally managed runtime such as llama-swap."""

    running_url: str
    running_contains: str
    start_url: str
    stop_url: str
    start_method: Literal["GET", "POST"] = "POST"
    stop_method: Literal["GET", "POST"] = "POST"
    timeout_seconds: float = Field(default=10.0, gt=0)
    poll_interval_seconds: float = Field(default=1.0, gt=0)
    transition_timeout_seconds: float = Field(default=90.0, gt=0)


class ExternalGateConfig(BaseModel):
    """Optional request gate that must be drained before the LLM is unloaded."""

    status_url: str
    quiesce_url: str
    close_url: str
    open_url: str
    in_flight_field: str = "in_flight"
    timeout_seconds: float = Field(default=10.0, gt=0)
    poll_interval_seconds: float = Field(default=0.5, gt=0)
    drain_timeout_seconds: float = Field(default=60.0, gt=0)


class GpuProbeConfig(BaseModel):
    index: int = Field(default=0, ge=0)
    max_memory_used_mib_when_free: int = Field(default=1024, ge=0)
    poll_interval_seconds: float = Field(default=1.0, gt=0)
    free_timeout_seconds: float = Field(default=90.0, gt=0)
    stable_samples: int = Field(default=3, ge=1)


class ForecastJobConfig(BaseModel):
    command: list[str]
    cwd: Path
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, gt=0)
    terminate_grace_seconds: float = Field(default=10.0, gt=0)

    @model_validator(mode="after")
    def _command_is_not_empty(self) -> ForecastJobConfig:
        if not self.command:
            raise ValueError("forecast command must not be empty")
        return self


class SupervisorConfig(BaseModel):
    qwen: HttpRuntimeConfig
    gpu: GpuProbeConfig = Field(default_factory=GpuProbeConfig)
    forecast: ForecastJobConfig
    gate: ExternalGateConfig | None = None
    output_dir: Path
    lock_path: Path = Path("/tmp/loto-gpu-exclusive.lock")
    require_qwen_initially_running: bool = False
    restore_qwen_if_initially_running: bool = True
    monitor_qwen_during_forecast: bool = True

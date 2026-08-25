"""Configuration and state models for exclusive and adaptive GPU handoff."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SupervisorState(StrEnum):
    IDLE = "IDLE"
    DRAINING = "DRAINING"
    RESIDENCY_DECIDING = "RESIDENCY_DECIDING"
    COEXIST_READY = "COEXIST_READY"
    QWEN_STOPPING = "QWEN_STOPPING"
    GPU_FREE = "GPU_FREE"
    FORECAST_RUNNING = "FORECAST_RUNNING"
    FORECAST_STOPPING = "FORECAST_STOPPING"
    LLM_CONTINUITY_CHECK = "LLM_CONTINUITY_CHECK"
    QWEN_RESTORING = "QWEN_RESTORING"
    QWEN_READY = "QWEN_READY"
    FAILED = "FAILED"


class ResidencyMode(StrEnum):
    AUTO = "auto"
    COEXIST = "coexist"
    HANDOFF = "handoff"
    BLOCK = "block"


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
    """Optional request gate that must be drained before forecast GPU use."""

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


class ResidencyProfileSelector(BaseModel):
    """Exact tuple used to select one previously certified residency profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    llm_alias: str = Field(min_length=1)
    llm_runtime: str = Field(min_length=1)
    llm_context_length: int = Field(gt=0)
    foundation_repo_id: str = Field(min_length=1)
    foundation_revision: str = Field(min_length=1)
    runtime_lane: str = Field(min_length=1)


class GpuResidencyPolicy(BaseModel):
    """Operator-only adaptive residency policy.

    The library default is deliberately HANDOFF for backwards compatibility.
    AUTO can select COEXIST only when exact certified external VRAM evidence exists.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["auto", "coexist", "handoff"] = "handoff"
    resource_profile_path: Path | None = None
    profile_selector: ResidencyProfileSelector | None = None
    hard_reserve_mib: int = Field(default=2048, ge=0)
    reserve_ratio: float = Field(default=0.12, ge=0.0, le=1.0)
    foundation_peak_safety_factor: float = Field(default=1.25, ge=1.0)
    minimum_foundation_budget_mib: int = Field(default=1024, ge=0)
    unknown_profile_action: Literal["handoff", "block"] = "handoff"
    require_external_peak_evidence: bool = True
    require_exact_llm_identity: bool = True
    require_llm_pid_stability_when_available: bool = True
    post_run_vram_tolerance_mib: int = Field(default=256, ge=0)


class ResidencyGpuIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    uuid: str = Field(min_length=1)
    index: int = Field(ge=0)


class ResidencyLlmIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    alias: str = Field(min_length=1)
    runtime: str = Field(min_length=1)
    context_length: int = Field(gt=0)
    process_names: list[str] = Field(default_factory=list)


class ResidencyFoundationIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repo_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    runtime_lane: str = Field(min_length=1)


class ResidencyEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    external_peak_vram_mib: int | None = Field(default=None, gt=0)
    sample_count: int = Field(default=0, ge=0)
    certification_run_ids: list[str] = Field(default_factory=list)
    code_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class GpuResidencyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(min_length=1)
    certified: bool = False
    gpu: ResidencyGpuIdentity
    llm: ResidencyLlmIdentity
    foundation: ResidencyFoundationIdentity
    evidence: ResidencyEvidence


class GpuResidencyProfileRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    profiles: list[GpuResidencyProfile] = Field(default_factory=list)


class ResidencyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_mode: Literal["auto", "coexist", "handoff"]
    selected_mode: Literal["coexist", "handoff", "block"]
    decision_reason: str
    profile_id: str | None = None
    gpu_uuid: str | None = None
    gpu_total_mib: int | None = None
    gpu_used_before_mib: int | None = None
    gpu_free_before_mib: int | None = None
    foundation_peak_mib: int | None = None
    foundation_budget_mib: int | None = None
    safety_reserve_mib: int | None = None
    llm_gpu_pids_before: list[int] = Field(default_factory=list)
    foreign_gpu_pids_before: list[int] = Field(default_factory=list)
    fallback_triggered: bool = False


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
    residency: GpuResidencyPolicy = Field(default_factory=GpuResidencyPolicy)

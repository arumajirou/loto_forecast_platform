from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HarnessStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    VERIFIED = "VERIFIED"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    PENDING = "PENDING"


class EngineKind(StrEnum):
    LMSTUDIO = "lmstudio"
    LLAMACPP = "llamacpp"
    OPENAI_COMPATIBLE = "openai_compatible"
    GEMINI = "gemini"


class Capability(StrEnum):
    CHAT = "chat"
    EMBEDDING = "embedding"
    TOOLS = "tools"
    JSON_SCHEMA = "json_schema"
    REASONING = "reasoning"
    VISION = "vision"


class LoopPhase(StrEnum):
    OBSERVE = "OBSERVE"
    DIAGNOSE = "DIAGNOSE"
    PLAN = "PLAN"
    CHECKPOINT = "CHECKPOINT"
    CHANGE = "CHANGE"
    LOCAL_TEST = "LOCAL_TEST"
    MEASURE = "MEASURE"
    REVIEW = "REVIEW"
    JUDGE = "JUDGE"
    REPAIR = "REPAIR"
    ACCEPT = "ACCEPT"
    ROLLBACK = "ROLLBACK"
    FAILED = "FAILED"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    reasoning_content: str | None = None


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0


class EngineTimings(BaseModel):
    ttft_seconds: float | None = None
    total_seconds: float | None = None
    prompt_tokens_per_second: float | None = None
    generation_tokens_per_second: float | None = None


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[Message]
    temperature: float = Field(default=0.2, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    top_k: int | None = Field(default=None, ge=1)
    min_p: float | None = Field(default=None, ge=0, le=1)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    seed: int | None = None
    stop: list[str] | None = None
    max_tokens: int = Field(default=2048, ge=1)
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    system_instruction: str | None = None
    provider_history: list[dict[str, Any]] = Field(default_factory=list)
    profile_mode: str = "auto"
    task_type: str = "chat"
    extra_body: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    model: str
    content: str = ""
    reasoning_content: str | None = None
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    timings: EngineTimings = Field(default_factory=EngineTimings)
    raw: dict[str, Any] = Field(default_factory=dict)


class LoadRequest(BaseModel):
    model: str
    context_length: int = Field(default=65536, ge=1024)
    eval_batch_size: int | None = Field(default=None, ge=1)
    flash_attention: bool | None = True
    num_experts: int | None = Field(default=None, ge=1)
    offload_kv_cache_to_gpu: bool | None = True


class LoadedModel(BaseModel):
    model: str
    instance_id: str
    context_length: int
    status: HarnessStatus
    load_seconds: float | None = None
    applied_config: dict[str, Any] = Field(default_factory=dict)


class ModelPerformance(BaseModel):
    task_quality: float = Field(default=0.0, ge=0, le=1)
    tool_success: float = Field(default=0.0, ge=0, le=1)
    schema_success: float = Field(default=0.0, ge=0, le=1)
    test_pass_after_patch: float = Field(default=0.0, ge=0, le=1)
    reviewer_acceptance: float = Field(default=0.0, ge=0, le=1)
    stability: float = Field(default=0.0, ge=0, le=1)
    generation_tps: float = Field(default=0.0, ge=0)
    timeout_rate: float = Field(default=0.0, ge=0, le=1)
    oom_rate: float = Field(default=0.0, ge=0, le=1)


class ModelDescriptor(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str
    engine: EngineKind
    endpoint: str
    display_name: str | None = None
    capabilities: set[Capability] = Field(default_factory=lambda: {Capability.CHAT})
    declared_context: int = Field(default=8192, ge=1024)
    certified_context: int = Field(default=0, ge=0)
    virtual_context: int = Field(default=65536, ge=1024)
    quantization: str | None = None
    architecture: str | None = None
    provider: str | None = None
    profile_id: str | None = None
    enabled: bool = True
    status: HarnessStatus = HarnessStatus.DISCOVERED
    roles: set[str] = Field(default_factory=set)
    performance: ModelPerformance = Field(default_factory=ModelPerformance)
    loaded_instances: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("endpoint")
    @classmethod
    def normalize_endpoint(cls, value: str) -> str:
        return value.rstrip("/")


class HealthReport(BaseModel):
    engine: EngineKind
    endpoint: str
    status: HarnessStatus
    detail: str | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ContextPriority(StrEnum):
    PROTECTED = "protected"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class ContextItem(BaseModel):
    item_id: str
    kind: str
    content: str
    priority: ContextPriority = ContextPriority.NORMAL
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    token_estimate: int | None = None


class CompiledContext(BaseModel):
    content: str
    selected_ids: list[str]
    dropped_ids: list[str]
    raw_tokens: int
    final_tokens: int
    compression_ratio: float
    protected_loss: int
    context_sha256: str


class LoopLimits(BaseModel):
    max_iterations: int = Field(default=5, ge=1, le=50)
    max_same_failure_repeats: int = Field(default=2, ge=1, le=10)
    max_wall_seconds: int = Field(default=7200, ge=1)
    max_total_input_tokens: int = Field(default=500_000, ge=1)
    max_total_output_tokens: int = Field(default=100_000, ge=1)


class LoopTask(BaseModel):
    task_id: str
    objective: str
    repository: str
    worktree: str
    risk: RiskLevel = RiskLevel.MEDIUM
    acceptance_commands: list[list[str]] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    limits: LoopLimits = Field(default_factory=LoopLimits)


class LoopEvent(BaseModel):
    sequence: int
    phase: LoopPhase
    status: HarnessStatus
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LoopResult(BaseModel):
    task_id: str
    status: HarnessStatus
    final_phase: LoopPhase
    iterations: int
    events: list[LoopEvent]
    failure_signature: str | None = None

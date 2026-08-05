from __future__ import annotations

import hashlib
import json
import math
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EnvironmentLane(StrEnum):
    """Version-isolated GluonTS runtime lane."""

    COMPAT = "compat"
    LATEST = "latest"


class ProviderOperation(StrEnum):
    """Operation executed by the isolated provider process."""

    FIT_PREDICT = "fit_predict"
    LOAD_PREDICT = "load_predict"
    EVALUATE = "evaluate"
    BACKTEST = "backtest"
    MODEL_DISCOVERY = "model_discovery"
    DISTRIBUTION_DISCOVERY = "distribution_discovery"
    RUNTIME_CERTIFY = "runtime_certify"


class ProviderStatus(StrEnum):
    """Fail-closed provider result state."""

    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    EXECUTION_PENDING = "EXECUTION_PENDING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class DeviceRequest(StrEnum):
    """Requested execution device."""

    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"


class TimelineTrack(StrEnum):
    """Explicit timeline semantics used to construct a GluonTS Dataset."""

    DRAW_SEQUENCE = "draw_sequence"
    CALENDAR_TIME = "calendar_time"


class ArgumentState(StrEnum):
    """Classification for every requested constructor or API argument."""

    ACCEPTED = "ACCEPTED"
    TRANSFORMED = "TRANSFORMED"
    SUPPORTED_WITH_CONDITION = "SUPPORTED_WITH_CONDITION"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNSUPPORTED_BY_VERSION = "UNSUPPORTED_BY_VERSION"
    REJECTED = "REJECTED"
    DROPPED_WITH_REASON = "DROPPED_WITH_REASON"
    RUNTIME_VERIFIED = "RUNTIME_VERIFIED"


class ResourcePolicy(BaseModel):
    """Bounded outer concurrency and per-provider resource policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outer_workers: int = Field(default=8, ge=1, le=64)
    max_gpu_jobs: int = Field(default=1, ge=0, le=8)
    threads_per_job: int = Field(default=1, ge=1, le=64)

    @model_validator(mode="after")
    def validate_gpu_limit(self) -> ResourcePolicy:
        if self.max_gpu_jobs > self.outer_workers:
            raise ValueError("max_gpu_jobs cannot exceed outer_workers")
        return self


class DatasetItem(BaseModel):
    """JSON-safe subset of the GluonTS Dataset entry contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str = Field(min_length=1)
    start: str = Field(min_length=1)
    target: list[float] = Field(min_length=2)
    feat_static_cat: list[int] | None = None
    feat_static_real: list[float] | None = None
    feat_dynamic_real: list[list[float]] | None = None
    past_feat_dynamic_real: list[list[float]] | None = None

    @field_validator("target", "feat_static_real")
    @classmethod
    def validate_finite_vector(cls, values: list[float] | None) -> list[float] | None:
        if values is not None and not all(math.isfinite(value) for value in values):
            raise ValueError("numeric vectors must contain only finite values")
        return values

    @field_validator("feat_dynamic_real", "past_feat_dynamic_real")
    @classmethod
    def validate_finite_matrix(
        cls, values: list[list[float]] | None
    ) -> list[list[float]] | None:
        if values is not None and not all(
            math.isfinite(value) for row in values for value in row
        ):
            raise ValueError("numeric matrices must contain only finite values")
        return values


class GluonTSProviderRequest(BaseModel):
    """Version-independent request passed to a GluonTS subprocess over JSON."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    lane: EnvironmentLane
    operation: ProviderOperation
    model_class: str = Field(min_length=1)
    distribution_output: str | None = None
    prediction_length: int = Field(default=1, ge=1)
    context_length: int | None = Field(default=None, ge=1)
    seed: int = 1
    device: DeviceRequest = DeviceRequest.AUTO
    timeline_track: TimelineTrack = TimelineTrack.DRAW_SEQUENCE
    freq: str = Field(default="D", min_length=1)
    dataset: list[DatasetItem] = Field(default_factory=list)
    artifact_dir: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    resource_policy: ResourcePolicy = Field(default_factory=ResourcePolicy)

    @model_validator(mode="after")
    def validate_operation_contract(self) -> GluonTSProviderRequest:
        data_operations = {
            ProviderOperation.FIT_PREDICT,
            ProviderOperation.EVALUATE,
            ProviderOperation.BACKTEST,
        }
        if self.operation in data_operations and not self.dataset:
            raise ValueError(f"{self.operation.value} requires at least one dataset item")
        if self.operation is ProviderOperation.LOAD_PREDICT and not self.artifact_dir:
            raise ValueError("load_predict requires artifact_dir")
        if self.device is DeviceRequest.CUDA and self.resource_policy.max_gpu_jobs < 1:
            raise ValueError("CUDA requests require max_gpu_jobs >= 1")
        return self


class PredictionRow(BaseModel):
    """Identity-preserving point and quantile forecast row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str = Field(min_length=1)
    horizon: int = Field(ge=1)
    mean: float
    median: float | None = None
    quantiles: dict[str, float] = Field(default_factory=dict)

    @field_validator("mean", "median")
    @classmethod
    def validate_finite_scalar(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("prediction values must be finite")
        return value

    @field_validator("quantiles")
    @classmethod
    def validate_finite_quantiles(cls, values: dict[str, float]) -> dict[str, float]:
        if not all(math.isfinite(value) for value in values.values()):
            raise ValueError("quantile values must be finite")
        return values


class GluonTSProviderResponse(BaseModel):
    """Fail-closed provider response retained as a JSON artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    lane: EnvironmentLane
    status: ProviderStatus
    predictions: list[PredictionRow] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_contract(self) -> GluonTSProviderResponse:
        if self.status is ProviderStatus.VERIFIED and self.errors:
            raise ValueError("VERIFIED responses cannot contain errors")
        if self.status is ProviderStatus.FAILED and not self.errors:
            raise ValueError("FAILED responses must contain at least one error")
        return self


def protocol_schema_sha256() -> str:
    """Return a stable SHA-256 for the combined request/response JSON schemas."""

    payload = {
        "request": GluonTSProviderRequest.model_json_schema(),
        "response": GluonTSProviderResponse.model_json_schema(),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

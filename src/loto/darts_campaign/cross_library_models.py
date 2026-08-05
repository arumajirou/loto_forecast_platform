from __future__ import annotations

from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .cross_library_contract import (
    canonical_sha256,
    validate_sha256,
)


class CrossLibraryCertificationError(RuntimeError):
    """Raised when runtime evidence violates the comparison contract."""


class ForecastRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str = Field(min_length=1)
    seed: int
    fold_id: int
    origin: int = Field(ge=0)
    target_index: int = Field(ge=0)
    position: str = Field(min_length=1)
    actual: float
    predicted: float

    @model_validator(mode="after")
    def validate_record(self) -> ForecastRecord:
        if self.target_index < self.origin:
            raise ValueError("target_index must not precede origin")
        values = np.asarray([self.actual, self.predicted], dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("forecast records must be finite")
        return self

    def comparison_key(self) -> tuple[int, int, int, str]:
        return (self.seed, self.fold_id, self.target_index, self.position)


class ExecutionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str = Field(min_length=1)
    status: Literal["SUCCESS", "FAILED"]
    fairness_sha256: str
    data_sha256: str
    config_sha256: str
    code_sha256: str
    git_commit: str = Field(min_length=7)
    package_versions: dict[str, str]
    runtime_seconds: float | None = Field(default=None, ge=0.0)
    peak_memory_bytes: int | None = Field(default=None, ge=0)
    requested_device: Literal["cpu", "gpu"]
    effective_device: Literal["cpu", "gpu", "not_applicable"]
    gpu_evidence: dict[str, Any] = Field(default_factory=dict)
    records: tuple[ForecastRecord, ...] = ()
    failure_class: str | None = None
    failure_message: str | None = None

    @field_validator("fairness_sha256", "data_sha256", "config_sha256", "code_sha256")
    @classmethod
    def check_hash(cls, value: str, info: Any) -> str:
        return validate_sha256(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_status(self) -> ExecutionEvidence:
        if self.status == "SUCCESS":
            if not self.records:
                raise ValueError("successful execution requires forecast records")
            if self.failure_class or self.failure_message:
                raise ValueError("successful execution cannot contain failure evidence")
        else:
            if not self.failure_class:
                raise ValueError("failed execution requires failure_class")
            if self.records:
                raise ValueError("failed execution must not publish formal forecast records")
        if self.requested_device == "gpu" and self.status == "SUCCESS":
            if self.effective_device != "gpu":
                raise ValueError("successful GPU request cannot use CPU fallback")
            required = {
                "process_pid",
                "gpu_pid",
                "vram_before_bytes",
                "vram_peak_bytes",
                "vram_after_bytes",
            }
            missing = sorted(required - set(self.gpu_evidence))
            if missing:
                raise ValueError(f"GPU evidence is incomplete: {missing}")
        return self

    def prediction_sha256(self) -> str | None:
        if self.status != "SUCCESS":
            return None
        payload = [record.model_dump(mode="json") for record in self.records]
        return canonical_sha256(payload)


class MetricVector(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hit_at_plus_minus_1: float = Field(ge=0.0, le=1.0)
    all_position_hit_at_plus_minus_1: float = Field(ge=0.0, le=1.0)
    mae: float = Field(ge=0.0)
    mse: float = Field(ge=0.0)
    rmse: float = Field(ge=0.0)
    position_hit_at_plus_minus_1: dict[str, float]


class AggregateMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mean: MetricVector
    variance: MetricVector
    worst: MetricVector
    seed_metrics: dict[int, MetricVector]


class ProviderMetricResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str
    algorithm_key: str
    execution_key: str
    canonical_for_algorithm: bool
    metrics: AggregateMetric
    prediction_sha256: str
    record_count: int = Field(ge=1)


class WrapperComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    algorithm_key: str
    canonical_provider_id: str
    variant_provider_id: str
    comparison_key_count: int = Field(ge=1)
    max_abs_prediction_delta: float = Field(ge=0.0)
    mean_abs_prediction_delta: float = Field(ge=0.0)
    hit_at_plus_minus_1_delta: float
    all_position_hit_delta: float
    mae_delta: float
    prediction_parity_required: bool
    prediction_parity_passed: bool


class BaselineResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_id: str
    metrics: AggregateMetric


class ChampionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["CHAMPION", "NO_CHAMPION"]
    provider_id: str | None = None
    algorithm_key: str | None = None
    reason: str


class CrossLibraryReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fairness_sha256: str
    provider_results: tuple[ProviderMetricResult, ...]
    failed_provider_ids: tuple[str, ...]
    wrapper_comparisons: tuple[WrapperComparison, ...]
    canonical_algorithm_count: int = Field(ge=0)
    execution_count: int = Field(ge=0)
    champion: ChampionDecision
    report_sha256: str

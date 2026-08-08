from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)


class Operation(StrEnum):
    IDENTITY = "identity"
    DISCOVER = "discover"
    TRAIN_SAVE = "train_save"
    LOAD_PREDICT = "load_predict"
    VERIFY_ARTIFACT = "verify_artifact"


class TimeSemantics(StrEnum):
    DRAW_SEQUENCE = "draw_sequence"
    CALENDAR_TIME = "calendar_time"


class SeriesPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    values: list[float] = Field(min_length=3)
    draw_numbers: list[StrictInt] | None = None
    timestamps: list[datetime] | None = None

    @model_validator(mode="after")
    def validate_lengths(self) -> SeriesPayload:
        expected = len(self.values)
        if self.draw_numbers is not None and len(self.draw_numbers) != expected:
            raise ValueError("draw_numbers and values must have equal length")
        if self.timestamps is not None and len(self.timestamps) != expected:
            raise ValueError("timestamps and values must have equal length")
        return self


class ProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["merlion-provider-v1"] = "merlion-provider-v1"
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    operation: Operation
    model_name: Literal["Arima", "ETS", "MSES"] | None = None
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        alias="model_config",
        serialization_alias="model_config",
    )
    series: SeriesPayload | None = None
    time_semantics: TimeSemantics = TimeSemantics.DRAW_SEQUENCE
    horizon: StrictInt = Field(default=1, ge=1, le=1000)
    artifact_subdir: str = Field(default="model", pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
    expected_manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @field_validator("artifact_subdir")
    @classmethod
    def reject_unsafe_artifact_path(cls, value: str) -> str:
        parts = value.replace("\\", "/").split("/")
        if value.startswith("/") or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("artifact_subdir must be a safe relative path")
        return value

    @model_validator(mode="after")
    def validate_operation_payload(self) -> ProviderRequest:
        lifecycle = {Operation.TRAIN_SAVE, Operation.LOAD_PREDICT}
        if self.operation in lifecycle and self.model_name is None:
            raise ValueError("model_name is required for lifecycle operations")
        if self.operation is Operation.TRAIN_SAVE and self.series is None:
            raise ValueError("series is required for train_save")
        if self.operation is Operation.LOAD_PREDICT and self.expected_manifest_sha256 is None:
            raise ValueError("expected_manifest_sha256 is required for load_predict")
        return self


class PredictionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamps: list[str]
    values: list[float]
    standard_errors: list[float] | None = None


class ProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["merlion-provider-response-v1"] = "merlion-provider-response-v1"
    request_id: str
    status: Literal["PASS", "FAILED", "BLOCKED"]
    phase: str
    message: str
    process_id: int
    evidence: dict[str, Any] = Field(default_factory=dict)
    prediction: PredictionPayload | None = None

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ArgumentStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNSUPPORTED_BY_VERSION = "UNSUPPORTED_BY_VERSION"
    REJECTED = "REJECTED"


class FailureClass(StrEnum):
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
    IMPORT_FAILED = "IMPORT_FAILED"
    INVALID_REQUEST = "INVALID_REQUEST"
    ARGUMENT_REJECTED = "ARGUMENT_REJECTED"
    FIT_FAILED = "FIT_FAILED"
    PREDICT_FAILED = "PREDICT_FAILED"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
    TIMEOUT = "TIMEOUT"


class SeriesLayout(StrEnum):
    POSITION_LOCAL = "position_local"
    POSITION_MULTIVARIATE = "position_multivariate"
    POSITION_GLOBAL_SEQUENCE = "position_global_sequence"
    CANDIDATE_BINARY = "candidate_binary"
    POSITION_DIGIT = "position_digit"


class RuntimeKind(StrEnum):
    NOTORCH = "notorch"
    TORCH = "torch"


class DevicePolicy(StrEnum):
    CPU = "cpu"
    CUDA = "cuda"
    AUTO = "auto"


class GameGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: str = Field(min_length=1)
    positions: int = Field(ge=1, le=20)
    min_value: int
    max_value: int
    draw_no_col: str = "draw_no"
    time_col: str = "draw_date"
    position_prefix: str = "n"

    @model_validator(mode="after")
    def validate_range(self) -> GameGeometry:
        if self.min_value > self.max_value:
            raise ValueError("min_value must be <= max_value")
        return self

    @property
    def position_columns(self) -> list[str]:
        return [f"{self.position_prefix}{index}" for index in range(1, self.positions + 1)]


class ModelIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    public_name: str = Field(min_length=1)
    module: str = "darts.models"
    class_name: str | None = None
    wrapper_name: str | None = None
    base_models: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_wrapper(self) -> ModelIdentity:
        if self.wrapper_name and not self.base_models:
            raise ValueError("wrapper_name requires at least one base model")
        return self


class ArgumentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    argument: str
    status: ArgumentStatus
    reason: str
    value_repr: str


class DartsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    run_id: str = Field(min_length=1)
    mode: Literal["discover", "fit_predict"]
    geometry: GameGeometry
    model: ModelIdentity | None = None
    series_layout: SeriesLayout = SeriesLayout.POSITION_LOCAL
    horizon: int = Field(default=1, ge=1, le=512)
    model_args: dict[str, Any] = Field(default_factory=dict)
    base_model_args: dict[str, dict[str, Any]] = Field(default_factory=dict)
    fit_args: dict[str, Any] = Field(default_factory=dict)
    predict_args: dict[str, Any] = Field(default_factory=dict)
    runtime: RuntimeKind = RuntimeKind.NOTORCH
    device: DevicePolicy = DevicePolicy.CPU
    seed: int = 1
    timeout_seconds: int = Field(default=900, ge=1, le=86400)
    artifact_dir: Path

    @model_validator(mode="after")
    def validate_mode_contract(self) -> DartsRequest:
        if self.mode == "fit_predict" and self.model is None:
            raise ValueError("fit_predict requires model identity")
        if self.mode == "discover" and self.model is not None:
            raise ValueError("discover must not include a model identity")
        if self.runtime == RuntimeKind.NOTORCH and self.device != DevicePolicy.CPU:
            raise ValueError("notorch runtime only supports device=cpu")
        return self


class DartsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    run_id: str
    status: Literal["SUCCEEDED", "PARTIAL", "FAILED"]
    failure_class: FailureClass | None = None
    message: str | None = None
    predictions: list[list[float]] | None = None
    model_inventory: list[dict[str, Any]] | None = None
    argument_ledger: list[ArgumentDecision] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

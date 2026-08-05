from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

UPSTREAM_REPOSITORY = "https://github.com/thuml/Time-Series-Library"
UPSTREAM_REVISION = "4e938a1767106324dd753b2a44832bf870a0252e"
PROTOCOL_VERSION = "1.0"


class SourcePolicy(StrEnum):
    PINNED = "pinned"
    TEST_FIXTURE = "test_fixture"


class ProviderStatus(StrEnum):
    PASS = "PASS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class Operation(StrEnum):
    DISCOVER = "discover"
    DLINEAR_FIT_SAVE = "dlinear_fit_save"
    DLINEAR_LOAD_PREDICT = "dlinear_load_predict"
    VERIFY_ROUNDTRIP = "verify_roundtrip"


class GameGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: str = Field(min_length=1)
    position_columns: tuple[str, ...] = Field(min_length=1)
    draw_number_column: str = "draw_no"
    draw_date_column: str = "draw_date"
    candidate_min: int
    candidate_max: int
    draw_order_semantics: Literal["draw_sequence"] = "draw_sequence"

    @model_validator(mode="after")
    def validate_geometry(self) -> GameGeometry:
        if len(set(self.position_columns)) != len(self.position_columns):
            raise ValueError("position_columns must be unique")
        if self.candidate_min > self.candidate_max:
            raise ValueError("candidate_min must be <= candidate_max")
        return self


class SplitContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    train_end_exclusive: int = Field(gt=0)
    validation_end_exclusive: int = Field(gt=0)
    holdout_end_exclusive: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_boundaries(self) -> SplitContract:
        if not (
            self.train_end_exclusive
            < self.validation_end_exclusive
            <= self.holdout_end_exclusive
        ):
            raise ValueError("required order: train_end < validation_end <= holdout_end")
        return self


class ProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    operation: Operation
    source_root: Path
    output_dir: Path
    model_name: str = "DLinear"
    source_policy: SourcePolicy = SourcePolicy.PINNED
    device: Literal["cpu"] = "cpu"
    seed: int = 1
    seq_len: int = Field(default=16, ge=4)
    pred_len: int = Field(default=1, ge=1)
    channels: int = Field(default=1, ge=1)
    train_steps: int = Field(default=1, ge=0, le=100)
    checkpoint_path: Path | None = None
    input_path: Path | None = None
    before_prediction_path: Path | None = None
    after_prediction_path: Path | None = None
    rtol: float = Field(default=1e-8, ge=0)
    atol: float = Field(default=1e-8, ge=0)

    @model_validator(mode="after")
    def validate_operation_fields(self) -> ProviderRequest:
        if self.operation == Operation.DLINEAR_LOAD_PREDICT and (
            self.checkpoint_path is None or self.input_path is None
        ):
            raise ValueError("load/predict requires checkpoint_path and input_path")
        if self.operation == Operation.VERIFY_ROUNDTRIP and (
            self.before_prediction_path is None or self.after_prediction_path is None
        ):
            raise ValueError("roundtrip verification requires both prediction paths")
        return self


class ProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    status: ProviderStatus
    operation: Operation
    upstream_repository: str = UPSTREAM_REPOSITORY
    upstream_revision: str = UPSTREAM_REVISION
    model_name: str
    artifacts: dict[str, str] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from loto.data_access_ledger.enums import (
    AccessOperation,
    DataRole,
    FoldRole,
    Stage,
    StateKind,
)

STRICT_CONFIG = ConfigDict(
    extra="forbid",
    strict=True,
    allow_inf_nan=False,
    validate_assignment=True,
)
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$"


def _require_utc(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must use UTC offset +00:00")
    return value.astimezone(UTC)


class DatasetSlice(BaseModel):
    model_config = STRICT_CONFIG

    dataset_id: str = Field(pattern=_ID_PATTERN)
    dataset_sha256: str = Field(pattern=_SHA256_PATTERN)
    data_role: DataRole
    game_id: str = Field(pattern=_ID_PATTERN)
    series_ids: list[str] = Field(min_length=1)
    row_start: int = Field(ge=0)
    row_end: int = Field(ge=0)
    observed_time_start: datetime
    observed_time_end: datetime
    available_at: datetime
    forecast_origin: datetime
    contains_targets: bool
    contains_actuals: bool
    immutable_source: bool
    fold_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    fold_role: FoldRole | None = None
    draw_id: str | None = Field(default=None, pattern=_ID_PATTERN)

    @field_validator("series_ids")
    @classmethod
    def validate_series_ids(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("series_ids must not contain blank values")
        if len(value) != len(set(value)):
            raise ValueError("series_ids must be unique")
        return value

    @field_validator(
        "observed_time_start",
        "observed_time_end",
        "available_at",
        "forecast_origin",
    )
    @classmethod
    def validate_utc_fields(cls, value: datetime, info) -> datetime:
        normalized = _require_utc(value, info.field_name)
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_slice(self) -> DatasetSlice:
        if self.row_start > self.row_end:
            raise ValueError("row_start must not exceed row_end")
        if self.observed_time_start > self.observed_time_end:
            raise ValueError("observed_time_start must not exceed observed_time_end")
        if self.contains_actuals and self.data_role is not DataRole.ACTUALS:
            raise ValueError("contains_actuals=true is only valid for ACTUALS role")
        if (self.fold_id is None) != (self.fold_role is None):
            raise ValueError("fold_id and fold_role must be provided together")
        return self


class StateReference(BaseModel):
    model_config = STRICT_CONFIG

    state_id: str = Field(pattern=_ID_PATTERN)
    state_kind: StateKind
    state_sha256: str = Field(pattern=_SHA256_PATTERN)
    fitted_event_id: str = Field(pattern=_ID_PATTERN)
    fitted_dataset_sha256: str = Field(pattern=_SHA256_PATTERN)
    fitted_data_role: DataRole
    fitted_row_start: int = Field(ge=0)
    fitted_row_end: int = Field(ge=0)
    bound_run_id: str = Field(pattern=_ID_PATTERN)
    authorized_reuse_run_ids: list[str] = Field(default_factory=list)
    fold_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    contains_actuals: bool = False

    @field_validator("authorized_reuse_run_ids")
    @classmethod
    def validate_reuse_ids(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("authorized_reuse_run_ids must not contain blank values")
        if len(value) != len(set(value)):
            raise ValueError("authorized_reuse_run_ids must be unique")
        return value

    @model_validator(mode="after")
    def validate_rows(self) -> StateReference:
        if self.fitted_row_start > self.fitted_row_end:
            raise ValueError("fitted_row_start must not exceed fitted_row_end")
        return self


class AccessEvent(BaseModel):
    model_config = STRICT_CONFIG

    event_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    sequence_no: int = Field(ge=1)
    stage: Stage
    operation: AccessOperation
    occurred_at: datetime
    actor: str = Field(min_length=1, max_length=256)
    input_slices: list[DatasetSlice] = Field(default_factory=list)
    input_states: list[StateReference] = Field(default_factory=list)
    output_state: StateReference | None = None
    parent_event_ids: list[str] = Field(default_factory=list)
    forecast_origin: datetime | None = None
    forecast_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    fold_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    seed: int | None = Field(default=None, ge=0)
    actuals_known: bool
    notes: str = Field(default="", max_length=4000)

    @field_validator("occurred_at", "forecast_origin")
    @classmethod
    def validate_utc_fields(cls, value: datetime | None, info) -> datetime | None:
        return _require_utc(value, info.field_name)

    @field_validator("parent_event_ids")
    @classmethod
    def validate_parent_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("parent_event_ids must be unique")
        return value

    @model_validator(mode="after")
    def validate_event(self) -> AccessEvent:
        if self.event_id in self.parent_event_ids:
            raise ValueError("parent_event_ids must not contain event_id")
        state_ids = [state.state_id for state in self.input_states]
        if len(state_ids) != len(set(state_ids)):
            raise ValueError("input state_ids must be unique")
        if self.stage is Stage.OOF and (self.fold_id is None or self.seed is None):
            raise ValueError("OOF events require fold_id and seed")
        return self


class DataAccessLedger(BaseModel):
    model_config = STRICT_CONFIG

    schema_version: Literal["1.0.0"] = "1.0.0"
    run_id: str = Field(pattern=_ID_PATTERN)
    created_at: datetime
    events: list[AccessEvent] = Field(min_length=1)
    event_count: int = Field(ge=1)
    first_event_at: datetime
    last_event_at: datetime
    ledger_sha256: str = Field(pattern=_SHA256_PATTERN)
    expected_seeds: list[int] = Field(default_factory=list)

    @field_validator("created_at", "first_event_at", "last_event_at")
    @classmethod
    def validate_utc_fields(cls, value: datetime, info) -> datetime:
        normalized = _require_utc(value, info.field_name)
        assert normalized is not None
        return normalized

    @field_validator("expected_seeds")
    @classmethod
    def validate_expected_seeds(cls, value: list[int]) -> list[int]:
        if any(seed < 0 for seed in value):
            raise ValueError("expected_seeds must be non-negative")
        if len(value) != len(set(value)):
            raise ValueError("expected_seeds must be unique")
        return value

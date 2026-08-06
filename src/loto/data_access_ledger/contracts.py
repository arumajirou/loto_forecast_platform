from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SplitRole(StrEnum):
    RAW = "raw"
    TRAIN = "train"
    VALIDATION = "validation"
    HOLDOUT = "holdout"
    PROSPECTIVE = "prospective"
    ACTUAL = "actual"


class AccessMode(StrEnum):
    READ = "read"
    WRITE = "write"
    FIT = "fit"
    TRANSFORM_FIT = "transform_fit"
    TRANSFORM_APPLY = "transform_apply"
    JOIN = "join"
    AGGREGATE = "aggregate"
    LABEL = "label"
    SCORE = "score"


class AccessPurpose(StrEnum):
    FEATURE_BUILD = "feature_build"
    MODEL_FIT = "model_fit"
    MODEL_SELECTION = "model_selection"
    HYPERPARAMETER_TUNING = "hyperparameter_tuning"
    EVALUATION = "evaluation"
    SCORING = "scoring"
    ACTUAL_INGESTION = "actual_ingestion"
    AUDIT = "audit"
    EXPORT = "export"


class TemporalScope(StrEnum):
    PAST_ONLY = "past_only"
    AS_OF = "as_of"
    FUTURE_KNOWN = "future_known"
    TARGET = "target"
    UNBOUNDED = "unbounded"


class ColumnRole(StrEnum):
    IDENTIFIER = "identifier"
    TIMESTAMP = "timestamp"
    FEATURE = "feature"
    TARGET = "target"
    METADATA = "metadata"
    ACTUAL = "actual"


class LedgerStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class TimeBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime | None = None
    end: datetime | None = None
    prediction_cutoff: datetime | None = None
    available_at: datetime | None = None
    inclusive_end: bool = True

    @model_validator(mode="after")
    def validate_order(self) -> TimeBoundary:
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start must not exceed end")
        return self


class ColumnAccess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=256)
    role: ColumnRole
    temporal_scope: TemporalScope
    lag: int = Field(default=0, ge=0)
    source_name: str | None = Field(default=None, min_length=1, max_length=256)
    known_at: datetime | None = None

    @field_validator("name", "source_name")
    @classmethod
    def reject_blank_names(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("column names must not be blank")
        return value


class CodeLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=1024)
    line: int = Field(ge=1)
    symbol: str | None = Field(default=None, min_length=1, max_length=256)

    @field_validator("path")
    @classmethod
    def require_repo_relative_posix_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("path must be repository-relative and must not contain '..'")
        return str(path)


class DataAccessEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    process_id: str = Field(min_length=1, max_length=128)
    sequence: int = Field(ge=0)
    mode: AccessMode
    purpose: AccessPurpose
    split: SplitRole
    dataset: str = Field(min_length=1, max_length=2048)
    columns: list[ColumnAccess] = Field(default_factory=list)
    boundary: TimeBoundary
    location: CodeLocation
    dependencies: list[str] = Field(default_factory=list)
    query_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evidence_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    notes: str = Field(default="", max_length=2000)

    @field_validator("dataset", "process_id")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("dependencies")
    @classmethod
    def require_unique_dependencies(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("dependencies must be unique")
        return value

    @model_validator(mode="after")
    def validate_event_shape(self) -> DataAccessEvent:
        if self.event_id in self.dependencies:
            raise ValueError("event must not depend on itself")
        if self.mode in {
            AccessMode.READ,
            AccessMode.FIT,
            AccessMode.TRANSFORM_FIT,
            AccessMode.TRANSFORM_APPLY,
            AccessMode.JOIN,
            AccessMode.AGGREGATE,
            AccessMode.LABEL,
            AccessMode.SCORE,
        } and not self.columns:
            raise ValueError(f"columns are required for mode={self.mode.value}")
        names = [column.name for column in self.columns]
        if len(names) != len(set(names)):
            raise ValueError("column names must be unique within an event")
        return self


class DataAccessLedger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"] = "1.0.0"
    ledger_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    generated_at: datetime
    code_revision: str = Field(pattern=r"^(?:[0-9a-f]{40}|UNCOMMITTED)$")
    events: list[DataAccessEvent] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_event_identity(self) -> DataAccessLedger:
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("event_id values must be unique")
        positions = [(event.sequence, event.event_id) for event in self.events]
        if positions != sorted(positions):
            raise ValueError("events must be sorted by sequence and event_id")
        return self


class LedgerFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=128)
    event_id: str
    message: str = Field(min_length=1, max_length=2000)


class LedgerReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ledger_id: str
    status: LedgerStatus
    findings: list[LedgerFinding]

    @property
    def passed(self) -> bool:
        return self.status is LedgerStatus.PASS

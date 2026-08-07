from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

STRICT_CONFIG = ConfigDict(
    extra="forbid",
    strict=True,
    allow_inf_nan=False,
    validate_assignment=True,
)


class DownstreamCommitStatus(StrEnum):
    PREPARED = "PREPARED"
    IN_PROGRESS = "IN_PROGRESS"
    RETRY_REQUIRED = "RETRY_REQUIRED"
    COMMITTED = "COMMITTED"


class DownstreamStepStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ArtifactSnapshotItem(BaseModel):
    model_config = STRICT_CONFIG

    relative_path: str = Field(min_length=1, max_length=500)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class PreparedDownstreamCommit(BaseModel):
    model_config = STRICT_CONFIG

    schema_version: str = "1.0.0"
    output_dir: str
    run_id: str = Field(min_length=1, max_length=200)
    commit_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    ledger_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    forecast_id: str = Field(min_length=1, max_length=200)
    draw_id: str = Field(min_length=1, max_length=200)
    model_id: str = Field(min_length=1, max_length=200)
    data_version: str = Field(min_length=1, max_length=500)
    feature_set_id: str = Field(min_length=1, max_length=500)
    release_id: str = Field(min_length=1, max_length=250)
    champion: str = Field(min_length=1, max_length=200)
    artifacts: list[ArtifactSnapshotItem] = Field(min_length=1)
    forecast: dict[str, Any]
    sealed_forecast: dict[str, Any]
    evaluation: dict[str, Any]
    metrics: dict[str, float]

    @model_validator(mode="after")
    def validate_artifacts(self) -> PreparedDownstreamCommit:
        names = [item.relative_path for item in self.artifacts]
        if len(names) != len(set(names)):
            raise ValueError("artifact relative_path values must be unique")
        return self

    @property
    def root(self) -> Path:
        return Path(self.output_dir)


class DownstreamStepState(BaseModel):
    model_config = STRICT_CONFIG

    name: str = Field(min_length=1, max_length=100)
    status: DownstreamStepStatus = DownstreamStepStatus.PENDING
    attempts: int = Field(default=0, ge=0)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = Field(default=None, max_length=4000)


class DownstreamCommitState(BaseModel):
    model_config = STRICT_CONFIG

    schema_version: str = "1.0.0"
    commit_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str
    ledger_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: DownstreamCommitStatus
    attempt_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime
    steps: list[DownstreamStepState]

    @model_validator(mode="after")
    def validate_steps(self) -> DownstreamCommitState:
        names = [item.name for item in self.steps]
        if len(names) != len(set(names)):
            raise ValueError("step names must be unique")
        return self


class DownstreamCommitReceipt(BaseModel):
    model_config = STRICT_CONFIG

    schema_version: str = "1.0.0"
    status: DownstreamCommitStatus
    commit_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str
    ledger_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    release_id: str
    forecast_id: str
    model_id: str
    committed_at: datetime
    step_results: dict[str, dict[str, Any]]
    non_claims: tuple[str, ...] = (
        "candidate registration only; no model promotion",
        "local HMAC forecast seal is not official trusted-time Prediction Lock",
        "no Actual Source verification",
        "no designated Holdout opening",
        "no runtime or GPU certification",
    )


def utc_now() -> datetime:
    return datetime.now(UTC)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()

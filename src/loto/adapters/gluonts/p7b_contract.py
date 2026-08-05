from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class P7BStage(StrEnum):
    PREFLIGHT = "preflight"
    COMPAT_BOOTSTRAP = "compat_bootstrap"
    LATEST_BOOTSTRAP = "latest_bootstrap"
    AUDIT = "audit"
    FINALIZE = "finalize"


class P7BStageState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    TIMED_OUT = "TIMED_OUT"
    INTERRUPTED = "INTERRUPTED"
    FAILED_TO_START = "FAILED_TO_START"
    SKIPPED = "SKIPPED"


class P7BExecutionState(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    INTERRUPTED = "INTERRUPTED"


TERMINAL_STAGE_STATES = {
    P7BStageState.COMPLETED,
    P7BStageState.TIMED_OUT,
    P7BStageState.INTERRUPTED,
    P7BStageState.FAILED_TO_START,
    P7BStageState.SKIPPED,
}


class P7BSourceIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repository_root: str = Field(min_length=1)
    branch: str = Field(min_length=1)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    tracked_worktree_dirty: bool
    source_sha256: dict[str, str] = Field(min_length=1)

    @field_validator("source_sha256")
    @classmethod
    def validate_source_hashes(cls, values: dict[str, str]) -> dict[str, str]:
        for path, digest in values.items():
            if not path or Path(path).is_absolute() or ".." in Path(path).parts:
                raise ValueError("source identity paths must be safe relative paths")
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise ValueError("source identity contains an invalid SHA-256")
        return values


class P7BStageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: P7BStage
    state: P7BStageState
    attempt: int = Field(ge=1)
    command: list[str] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    command_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    started_at_utc: str | None = None
    ended_at_utc: str | None = None
    process_id: int | None = Field(default=None, ge=1)
    process_group_id: int | None = Field(default=None, ge=1)
    return_code: int | None = None
    timeout_seconds: int | None = Field(default=None, ge=1)
    stdout_path: str | None = None
    stderr_path: str | None = None
    return_code_path: str | None = None
    artifact_root: str | None = None
    output_identity_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    errors: list[str] = Field(default_factory=list)

    @field_validator("started_at_utc", "ended_at_utc")
    @classmethod
    def validate_timestamp(cls, value: str | None) -> str | None:
        if value is not None:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @model_validator(mode="after")
    def validate_state(self) -> P7BStageRecord:
        if self.command and self.command_sha256 is None:
            raise ValueError("stage commands require command_sha256")
        if self.state is P7BStageState.PENDING:
            if any(
                value is not None
                for value in (
                    self.started_at_utc,
                    self.ended_at_utc,
                    self.process_id,
                    self.return_code,
                )
            ):
                raise ValueError("PENDING stage cannot contain execution evidence")
        elif self.state is P7BStageState.RUNNING:
            if self.started_at_utc is None or self.process_id is None:
                raise ValueError("RUNNING stage requires start time and PID")
            if self.ended_at_utc is not None or self.return_code is not None:
                raise ValueError("RUNNING stage cannot contain terminal evidence")
        elif self.state is P7BStageState.COMPLETED:
            if self.started_at_utc is None or self.ended_at_utc is None:
                raise ValueError("COMPLETED stage requires start and end times")
            if self.return_code is None:
                raise ValueError("COMPLETED stage requires a return code")
            if self.output_identity_sha256 is None:
                raise ValueError("COMPLETED stage requires output identity")
        elif self.state in {
            P7BStageState.TIMED_OUT,
            P7BStageState.INTERRUPTED,
            P7BStageState.FAILED_TO_START,
        }:
            if self.ended_at_utc is None or not self.errors:
                raise ValueError("failed terminal stage requires end time and errors")
        return self


class P7BExecutionJournal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    phase: Literal["P7B_TARGET_MACHINE_SUPERVISION"] = (
        "P7B_TARGET_MACHINE_SUPERVISION"
    )
    run_id: str = Field(min_length=1)
    output_directory: str = Field(min_length=1)
    started_at_utc: str
    updated_at_utc: str
    execution_state: P7BExecutionState
    resume_count: int = Field(ge=0)
    source_identity: P7BSourceIdentity
    stages: dict[P7BStage, P7BStageRecord]
    errors: list[str] = Field(default_factory=list)

    @field_validator("started_at_utc", "updated_at_utc")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @model_validator(mode="after")
    def validate_journal(self) -> P7BExecutionJournal:
        if set(self.stages) != set(P7BStage):
            raise ValueError("execution journal must contain every P7B stage")
        for stage, record in self.stages.items():
            if record.stage is not stage:
                raise ValueError("execution journal stage key/record mismatch")
        if self.execution_state is P7BExecutionState.COMPLETED:
            if any(record.state not in TERMINAL_STAGE_STATES for record in self.stages.values()):
                raise ValueError("completed execution requires terminal stage states")
            if self.stages[P7BStage.FINALIZE].state is not P7BStageState.COMPLETED:
                raise ValueError("completed execution requires completed finalization")
        if self.execution_state in {
            P7BExecutionState.BLOCKED,
            P7BExecutionState.INTERRUPTED,
        } and not self.errors:
            raise ValueError("non-completed terminal execution requires errors")
        return self


class P7BExecutionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    phase: Literal["P7B_TARGET_MACHINE_SUPERVISION"] = (
        "P7B_TARGET_MACHINE_SUPERVISION"
    )
    run_id: str = Field(min_length=1)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    journal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stage_command_sha256: dict[str, str]
    stage_output_identity_sha256: dict[str, str]
    audit_return_code: int | None = None
    finalized_at_utc: str

    @field_validator("finalized_at_utc")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @model_validator(mode="after")
    def validate_manifest(self) -> P7BExecutionManifest:
        expected_commands = {
            stage.value
            for stage in (
                P7BStage.COMPAT_BOOTSTRAP,
                P7BStage.LATEST_BOOTSTRAP,
                P7BStage.AUDIT,
            )
        }
        if set(self.stage_command_sha256) != expected_commands:
            raise ValueError("manifest command identities are incomplete")
        if not set(self.stage_output_identity_sha256).issuperset(expected_commands):
            raise ValueError("manifest output identities are incomplete")
        return self


def canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_json(payload: Any) -> str:
    return sha256_bytes(canonical_json_bytes(payload))


def atomic_write_json(path: Path, payload: Any) -> str:
    content = canonical_json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256_bytes(content)

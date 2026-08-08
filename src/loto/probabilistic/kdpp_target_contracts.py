from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from loto.probabilistic.kdpp_certification_gate import validate_sha256

MODEL_ID = "pp-k-dpp-fixed-k"
SCHEMA_VERSION = "1.0.0"
CONTROL_STATUS = "KDPP_TARGET_EXECUTION_PREPARED"
STAGES = (
    "SOURCE_HANDOFF_RECORDED",
    "KDPP_HISTORY_RECORDED",
    "CPU_FORMAL_RECORDED",
)

_EXPORTER_FILES = (
    "scripts/export_toto2_4m_raw_history.py",
    "scripts/verify_toto2_4m_raw_history_export.py",
    "scripts/manage_toto2_4m_history_approval.py",
    "src/loto/toto2_campaign/history_handoff.py",
)
_KDPP_FILES = (
    "scripts/materialize_kdpp_fixed_k_history.py",
    "scripts/run_kdpp_fixed_k_target_host.py",
    "scripts/certify_kdpp_fixed_k_runtime.py",
    "src/loto/probabilistic/kdpp_history_source.py",
    "src/loto/probabilistic/kdpp_certification_gate.py",
    "scripts/manage_kdpp_fixed_k_target_execution.py",
    "src/loto/probabilistic/kdpp_target_execution.py",
)
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class RepositoryIdentity(StrictModel):
    role: Literal["exporter", "kdpp"]
    root: str = Field(min_length=1)
    expected_head: str
    actual_head: str
    branch: str = Field(min_length=1)
    clean: Literal[True]
    python_executable: str = Field(min_length=1)
    file_sha256: dict[str, str]

    @field_validator("expected_head", "actual_head")
    @classmethod
    def git_sha(cls, value: str) -> str:
        if _GIT_SHA_RE.fullmatch(value) is None:
            raise ValueError("expected a lowercase 40-character Git SHA")
        return value

    @field_validator("file_sha256")
    @classmethod
    def file_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        for digest in value.values():
            validate_sha256(digest)
        return value

    @model_validator(mode="after")
    def head_matches(self) -> RepositoryIdentity:
        if self.actual_head != self.expected_head:
            raise ValueError("repository HEAD does not match the expected SHA")
        return self


class TargetExecutionPlan(StrictModel):
    schema_version: Literal[SCHEMA_VERSION]
    model_id: Literal[MODEL_ID]
    status: Literal[CONTROL_STATUS]
    run_id: str
    created_at_utc: datetime
    exporter: RepositoryIdentity
    kdpp: RepositoryIdentity
    game: Literal["numbers3", "numbers4", "miniloto", "loto6", "loto7"]
    position: int | None = Field(default=None, ge=1, le=4)
    prediction_length: Literal[1, 2, 5]
    seed: int
    samples_per_horizon: int = Field(ge=1)
    rbf_gamma: float = Field(gt=0)
    quality_pseudocount: float = Field(gt=0)
    psd_tolerance: float = Field(gt=0)
    config_sha256: str
    source_revision: str
    workspace: str = Field(min_length=1)
    holdout_opened: Literal[False]
    prospective_opened: Literal[False]
    automatic_approval: Literal[False]

    @field_validator("run_id")
    @classmethod
    def run_id_format(cls, value: str) -> str:
        if _RUN_ID_RE.fullmatch(value) is None:
            raise ValueError("run_id contains unsupported characters")
        return value

    @field_validator("created_at_utc", mode="before")
    @classmethod
    def parse_time(cls, value: object) -> object:
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @field_validator("created_at_utc")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("created_at_utc must be UTC")
        return value

    @field_validator("config_sha256")
    @classmethod
    def config_hash(cls, value: str) -> str:
        return validate_sha256(value)

    @field_validator("source_revision")
    @classmethod
    def source_git_sha(cls, value: str) -> str:
        if _GIT_SHA_RE.fullmatch(value) is None:
            raise ValueError("source_revision must be a lowercase Git SHA")
        return value

    @model_validator(mode="after")
    def game_geometry(self) -> TargetExecutionPlan:
        if self.game in {"numbers3", "numbers4"}:
            limit = 3 if self.game == "numbers3" else 4
            if self.position is None or self.position > limit:
                raise ValueError("Numbers3/4 require a valid position")
        elif self.position is not None:
            raise ValueError("unordered games do not accept position")
        if self.source_revision != self.kdpp.actual_head:
            raise ValueError("source_revision must equal the k-DPP checkout HEAD")
        return self


class ControlState(StrictModel):
    schema_version: Literal[SCHEMA_VERSION]
    model_id: Literal[MODEL_ID]
    run_id: str
    current_stage: Literal[
        "PREPARED",
        "SOURCE_HANDOFF_RECORDED",
        "KDPP_HISTORY_RECORDED",
        "CPU_FORMAL_RECORDED",
    ]
    event_count: int = Field(ge=0, le=3)
    last_event_sha256: str | None

    @field_validator("last_event_sha256")
    @classmethod
    def optional_hash(cls, value: str | None) -> str | None:
        return validate_sha256(value) if value is not None else value


class ExecutionEvent(StrictModel):
    schema_version: Literal[SCHEMA_VERSION]
    model_id: Literal[MODEL_ID]
    run_id: str
    event_index: int = Field(ge=1, le=3)
    stage: Literal[
        "SOURCE_HANDOFF_RECORDED",
        "KDPP_HISTORY_RECORDED",
        "CPU_FORMAL_RECORDED",
    ]
    recorded_at_utc: datetime
    previous_event_sha256: str | None
    artifact_paths: dict[str, str]
    artifact_sha256: dict[str, str]
    summary: dict[str, Any]
    event_sha256: str

    @field_validator("recorded_at_utc", mode="before")
    @classmethod
    def parse_time(cls, value: object) -> object:
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @field_validator("recorded_at_utc")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("recorded_at_utc must be UTC")
        return value

    @field_validator("previous_event_sha256")
    @classmethod
    def previous_hash(cls, value: str | None) -> str | None:
        return validate_sha256(value) if value is not None else value

    @field_validator("artifact_sha256")
    @classmethod
    def artifact_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        for digest in value.values():
            validate_sha256(digest)
        return value

    @field_validator("event_sha256")
    @classmethod
    def event_hash(cls, value: str) -> str:
        return validate_sha256(value)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def canonical_json_bytes(payload: Any) -> bytes:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (serialized + "\n").encode("utf-8")


def _write_json(path: Path, payload: Any) -> None:
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_bytes(canonical_json_bytes(payload))
    temporary.replace(path)


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()

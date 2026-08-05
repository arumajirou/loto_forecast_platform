from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class P7DVerificationState(StrEnum):
    VERIFIED = "VERIFIED"


class P7DBundleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            value.startswith("/")
            or "\\" in value
            or path.is_absolute()
            or ".." in path.parts
            or path.parts[0] != "run"
        ):
            raise ValueError("bundle entry must be a safe path below run/")
        return value


class P7DBundleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    phase: Literal["P7D_EVIDENCE_HANDOFF"] = "P7D_EVIDENCE_HANDOFF"
    run_id: str = Field(min_length=1)
    source_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    created_at_utc: str
    compression: Literal["ZIP_DEFLATE_LEVEL_6"] = "ZIP_DEFLATE_LEVEL_6"
    p7b_execution_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p7b_execution_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p7c_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p7c_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    orchestration_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    audit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    failure_matrix_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p7b_return_code: int
    p7c_return_code: Literal[0, 10, 20]
    evidence_state: str = Field(min_length=1)
    certification_status: str = Field(min_length=1)
    verified_model_lifecycles: int = Field(ge=0, le=18)
    p8_eligible: bool
    entries: list[P7DBundleEntry] = Field(min_length=1)

    @field_validator("created_at_utc")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @model_validator(mode="after")
    def validate_manifest(self) -> P7DBundleManifest:
        paths = [entry.path for entry in self.entries]
        if len(paths) != len(set(paths)):
            raise ValueError("bundle manifest contains duplicate entry paths")
        gate = (
            self.evidence_state == "VALID"
            and self.certification_status == "VERIFIED"
            and self.verified_model_lifecycles == 18
            and self.p7c_return_code == 0
        )
        if self.p8_eligible != gate:
            raise ValueError("P7D manifest P8 gate is inconsistent")
        return self


class P7DVerificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    phase: Literal["P7D_EVIDENCE_HANDOFF"] = "P7D_EVIDENCE_HANDOFF"
    verification_state: Literal[P7DVerificationState.VERIFIED] = (
        P7DVerificationState.VERIFIED
    )
    archive_path: str = Field(min_length=1)
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bundle_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bundle_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    source_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    entry_count: int = Field(ge=1)
    total_payload_bytes: int = Field(ge=0)
    evidence_state: str = Field(min_length=1)
    certification_status: str = Field(min_length=1)
    verified_model_lifecycles: int = Field(ge=0, le=18)
    p8_eligible: bool
    verified_at_utc: str

    @field_validator("verified_at_utc")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


def canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: Any) -> str:
    content = canonical_json_bytes(payload)
    atomic_write_bytes(path, content)
    return sha256_bytes(content)

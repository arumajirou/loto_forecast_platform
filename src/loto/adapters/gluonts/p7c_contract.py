from __future__ import annotations

import hashlib
import json
import os
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class P7CRemediationClass(StrEnum):
    VERIFIED = "VERIFIED"
    EVIDENCE_REPAIR = "EVIDENCE_REPAIR"
    ENVIRONMENT_REPAIR = "ENVIRONMENT_REPAIR"
    IMPLEMENTATION_REPAIR = "IMPLEMENTATION_REPAIR"
    TRANSIENT_RETRY = "TRANSIENT_RETRY"
    MANUAL_TRIAGE = "MANUAL_TRIAGE"


class P7CPriority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class P7CRerunScope(StrEnum):
    NONE = "NONE"
    LANE_CAMPAIGN = "LANE_CAMPAIGN"
    FULL_CROSS_LANE = "FULL_CROSS_LANE"


class P7CInputIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    p7b_output_directory: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    execution_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    audit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    failure_matrix_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class P7CRemediationItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str = Field(min_length=1)
    lane: Literal["compat", "latest", "cross_lane"]
    model_class: str = Field(min_length=1)
    current_status: str = Field(min_length=1)
    failed_stage: str = Field(min_length=1)
    failure_category: str | None = None
    remediation_class: P7CRemediationClass
    priority: P7CPriority
    rerun_scope: P7CRerunScope
    preserve_verified: bool
    action: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    errors: list[str] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    artifact_manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    commands: list[str] = Field(default_factory=list)

    @field_validator("evidence_paths")
    @classmethod
    def validate_paths(cls, values: list[str]) -> list[str]:
        for value in values:
            path = Path(value)
            if not value or path.is_absolute() or ".." in path.parts:
                raise ValueError("evidence paths must be safe relative paths")
        return values

    @model_validator(mode="after")
    def validate_item(self) -> P7CRemediationItem:
        if self.remediation_class is P7CRemediationClass.VERIFIED:
            if self.current_status != "VERIFIED":
                raise ValueError("VERIFIED remediation requires VERIFIED status")
            if self.failure_category is not None or self.errors:
                raise ValueError("VERIFIED remediation cannot contain failures")
            if self.rerun_scope is not P7CRerunScope.NONE:
                raise ValueError("VERIFIED remediation cannot request a rerun")
            if self.priority is not P7CPriority.P4:
                raise ValueError("VERIFIED remediation must use P4")
            if self.commands:
                raise ValueError("VERIFIED remediation cannot contain commands")
        else:
            if self.failure_category is None:
                raise ValueError("non-VERIFIED remediation requires a failure category")
            if not self.errors:
                raise ValueError("non-VERIFIED remediation requires errors")
            if self.rerun_scope is P7CRerunScope.NONE:
                raise ValueError("non-VERIFIED remediation requires a rerun scope")
        return self


class P7CRemediationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    phase: Literal["P7C_RESULT_TRIAGE_AND_REMEDIATION"] = "P7C_RESULT_TRIAGE_AND_REMEDIATION"
    source: P7CInputIdentity
    evidence_state: str = Field(min_length=1)
    certification_status: str = Field(min_length=1)
    verified_model_lifecycles: int = Field(ge=0, le=18)
    p8_eligible: bool
    counts: dict[str, int] = Field(default_factory=dict)
    items: list[P7CRemediationItem]
    recommended_next_action: str = Field(min_length=1)
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_plan(self) -> P7CRemediationPlan:
        ids = [item.item_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("P7C remediation item IDs must be unique")
        model_items = [item for item in self.items if item.lane != "cross_lane"]
        verified_count = sum(
            item.remediation_class is P7CRemediationClass.VERIFIED for item in model_items
        )
        if verified_count != self.verified_model_lifecycles:
            raise ValueError("verified lifecycle count does not match remediation rows")
        eligible = (
            self.evidence_state == "VALID"
            and self.certification_status == "VERIFIED"
            and self.verified_model_lifecycles == 18
            and len(model_items) == 18
            and all(item.remediation_class is P7CRemediationClass.VERIFIED for item in model_items)
            and not any(item.lane == "cross_lane" for item in self.items)
        )
        if self.p8_eligible != eligible:
            raise ValueError("P8 eligibility does not match P7C evidence")
        computed: dict[str, int] = {}
        for item in self.items:
            key = item.remediation_class.value
            computed[key] = computed.get(key, 0) + 1
        if self.counts and self.counts != dict(sorted(computed.items())):
            raise ValueError("P7C counts do not match remediation rows")
        object.__setattr__(self, "counts", dict(sorted(computed.items())))
        return self


def canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
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

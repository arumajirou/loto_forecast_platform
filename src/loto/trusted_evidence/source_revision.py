"""Source revision evidence for ETag, publication IDs, commits, and related identities."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .canonical import canonical_sha256
from .model_base import (
    SCHEMA_VERSION,
    SHA256_PATTERN,
    MaterialBoundEvidence,
    require_timezone,
)
from .statuses import EvidenceStatus, RevisionKind


class SourceRevisionEvidence(MaterialBoundEvidence):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    evidence_id: str = Field(min_length=1, max_length=256)
    status: EvidenceStatus
    revision_kind: RevisionKind
    revision_value: str | None = Field(default=None, min_length=1, max_length=2048)
    revision_value_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    observed_at_utc: datetime | None = None
    verifier_id: str | None = Field(default=None, min_length=1, max_length=256)

    @field_validator("observed_at_utc")
    @classmethod
    def validate_observed_at(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_timezone(value, "observed_at_utc")

    @model_validator(mode="after")
    def validate_status(self) -> SourceRevisionEvidence:
        allowed = {
            EvidenceStatus.NOT_PROVIDED,
            EvidenceStatus.OPERATOR_ASSERTED,
            EvidenceStatus.OFFICIAL_SOURCE_UNVERIFIED,
            EvidenceStatus.OFFICIAL_SOURCE_VERIFIED,
            EvidenceStatus.CORRECTED,
            EvidenceStatus.REVOKED,
        }
        if self.status not in allowed:
            raise ValueError(f"status is not valid for source revision: {self.status}")
        if self.status == EvidenceStatus.NOT_PROVIDED:
            if self.revision_kind != RevisionKind.NONE or self.revision_value is not None:
                raise ValueError("NOT_PROVIDED source revision must be empty")
            return self
        if (
            self.revision_kind == RevisionKind.NONE
            or self.revision_value is None
            or self.revision_value_sha256 is None
            or self.observed_at_utc is None
        ):
            raise ValueError("source revision requires kind, value, hash, and observation time")
        expected = canonical_sha256(self.revision_value)
        if self.revision_value_sha256 != expected:
            raise ValueError("source revision value SHA-256 mismatch")
        if self.status == EvidenceStatus.OFFICIAL_SOURCE_VERIFIED:
            if self.verifier_id is None or not self.verification_materials:
                raise ValueError("verified source revision requires verifier and material")
        return self

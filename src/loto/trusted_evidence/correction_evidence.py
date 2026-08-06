"""Hash-chained correction and revocation evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .canonical import canonical_sha256
from .model_base import SCHEMA_VERSION, SHA256_PATTERN, StrictModel, require_timezone
from .statuses import EvidenceStatus


class CorrectionEvidence(StrictModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    correction_id: str = Field(min_length=1, max_length=256)
    sequence_number: int = Field(ge=1)
    status: EvidenceStatus
    subject_evidence_sha256: str = Field(pattern=SHA256_PATTERN)
    previous_correction_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    replacement_evidence_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    reason: str = Field(min_length=1, max_length=4096)
    actor: str = Field(min_length=1, max_length=512)
    recorded_at_utc: datetime
    record_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("recorded_at_utc")
    @classmethod
    def validate_recorded_at(cls, value: datetime) -> datetime:
        return require_timezone(value, "correction recorded_at_utc")

    def hash_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"record_sha256"})

    @model_validator(mode="after")
    def validate_correction(self) -> CorrectionEvidence:
        if self.status not in {EvidenceStatus.CORRECTED, EvidenceStatus.REVOKED}:
            raise ValueError("correction status must be CORRECTED or REVOKED")
        if self.sequence_number == 1 and self.previous_correction_sha256 is not None:
            raise ValueError("first correction must not link a previous correction")
        if self.sequence_number > 1 and self.previous_correction_sha256 is None:
            raise ValueError("later corrections require previous correction SHA-256")
        if self.status == EvidenceStatus.CORRECTED:
            if self.replacement_evidence_sha256 is None:
                raise ValueError("CORRECTED requires replacement evidence SHA-256")
        elif self.replacement_evidence_sha256 is not None:
            raise ValueError("REVOKED must not contain replacement evidence")
        if self.record_sha256 != canonical_sha256(self.hash_payload()):
            raise ValueError("correction record SHA-256 mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        correction_id: str,
        sequence_number: int,
        status: EvidenceStatus,
        subject_evidence_sha256: str,
        previous_correction_sha256: str | None,
        replacement_evidence_sha256: str | None,
        reason: str,
        actor: str,
        recorded_at_utc: datetime,
    ) -> CorrectionEvidence:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "correction_id": correction_id,
            "sequence_number": sequence_number,
            "status": status,
            "subject_evidence_sha256": subject_evidence_sha256,
            "previous_correction_sha256": previous_correction_sha256,
            "replacement_evidence_sha256": replacement_evidence_sha256,
            "reason": reason,
            "actor": actor,
            "recorded_at_utc": recorded_at_utc,
        }
        draft = cls.model_construct(**payload, record_sha256="0" * 64)
        digest = canonical_sha256(draft.model_dump(mode="json", exclude={"record_sha256"}))
        return cls(**payload, record_sha256=digest)

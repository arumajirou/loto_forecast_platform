"""Additive evidence bundle bound to existing lock and seal file hashes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .actual_source import ActualSourceEvidence
from .canonical import canonical_sha256
from .correction_evidence import CorrectionEvidence
from .model_base import SCHEMA_VERSION, SHA256_PATTERN, StrictModel, require_timezone
from .signature_evidence import SignatureEvidence
from .time_evidence import TrustedTimeEvidence


class ThirdPartyEvidenceBundle(StrictModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    bundle_id: str = Field(min_length=1, max_length=256)
    prediction_lock_sha256: str = Field(pattern=SHA256_PATTERN)
    verification_seal_sha256: str = Field(pattern=SHA256_PATTERN)
    actuals_lock_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    created_at_utc: datetime
    trusted_time: list[TrustedTimeEvidence] = Field(default_factory=list)
    signatures: list[SignatureEvidence] = Field(default_factory=list)
    actual_source: ActualSourceEvidence | None = None
    corrections: list[CorrectionEvidence] = Field(default_factory=list)
    bundle_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("created_at_utc")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return require_timezone(value, "bundle created_at_utc")

    def hash_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"bundle_sha256"})

    @model_validator(mode="after")
    def validate_bundle_hash(self) -> ThirdPartyEvidenceBundle:
        if self.bundle_sha256 != canonical_sha256(self.hash_payload()):
            raise ValueError("evidence bundle SHA-256 mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        bundle_id: str,
        prediction_lock_sha256: str,
        verification_seal_sha256: str,
        actuals_lock_sha256: str | None,
        created_at_utc: datetime,
        trusted_time: list[TrustedTimeEvidence] | None = None,
        signatures: list[SignatureEvidence] | None = None,
        actual_source: ActualSourceEvidence | None = None,
        corrections: list[CorrectionEvidence] | None = None,
    ) -> ThirdPartyEvidenceBundle:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "bundle_id": bundle_id,
            "prediction_lock_sha256": prediction_lock_sha256,
            "verification_seal_sha256": verification_seal_sha256,
            "actuals_lock_sha256": actuals_lock_sha256,
            "created_at_utc": created_at_utc,
            "trusted_time": trusted_time or [],
            "signatures": signatures or [],
            "actual_source": actual_source,
            "corrections": corrections or [],
        }
        draft = cls.model_construct(**payload, bundle_sha256="0" * 64)
        digest = canonical_sha256(draft.model_dump(mode="json", exclude={"bundle_sha256"}))
        return cls(**payload, bundle_sha256=digest)

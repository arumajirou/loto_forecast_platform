"""Trusted-time evidence schema with explicit local and external boundaries."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .model_base import (
    SCHEMA_VERSION,
    SHA256_PATTERN,
    MaterialBoundEvidence,
    require_timezone,
)
from .statuses import EvidenceStatus, TimestampAuthority


class TrustedTimeEvidence(MaterialBoundEvidence):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    evidence_id: str = Field(min_length=1, max_length=256)
    status: EvidenceStatus
    subject_sha256: str = Field(pattern=SHA256_PATTERN)
    claimed_time_utc: datetime | None = None
    recorded_at_utc: datetime | None = None
    authority: TimestampAuthority
    authority_name: str | None = Field(default=None, min_length=1, max_length=512)
    verifier_id: str | None = Field(default=None, min_length=1, max_length=256)

    @field_validator("claimed_time_utc", "recorded_at_utc")
    @classmethod
    def validate_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_timezone(value, "trusted time")

    @model_validator(mode="after")
    def validate_status(self) -> TrustedTimeEvidence:
        external = {
            EvidenceStatus.EXTERNALLY_TIMESTAMPED_UNVERIFIED,
            EvidenceStatus.EXTERNALLY_TIMESTAMPED_VERIFIED,
        }
        if self.status == EvidenceStatus.NOT_PROVIDED:
            if self.authority != TimestampAuthority.NONE or self.claimed_time_utc is not None:
                raise ValueError("NOT_PROVIDED trusted time must not claim a timestamp")
        elif self.status == EvidenceStatus.OPERATOR_ASSERTED:
            if self.authority != TimestampAuthority.OPERATOR or self.claimed_time_utc is None:
                raise ValueError("OPERATOR_ASSERTED requires an operator timestamp")
        elif self.status == EvidenceStatus.LOCALLY_TIMESTAMPED:
            if self.authority != TimestampAuthority.LOCAL_SYSTEM:
                raise ValueError("LOCALLY_TIMESTAMPED requires LOCAL_SYSTEM authority")
            if self.claimed_time_utc is None or self.recorded_at_utc is None:
                raise ValueError("local timestamp requires claimed and recorded times")
            if self.verifier_id is not None:
                raise ValueError("local system time must not claim an external verifier")
        elif self.status in external:
            if self.authority in {
                TimestampAuthority.NONE,
                TimestampAuthority.OPERATOR,
                TimestampAuthority.LOCAL_SYSTEM,
            }:
                raise ValueError("external timestamp requires an external authority")
            if self.claimed_time_utc is None or not self.verification_materials:
                raise ValueError("external timestamp requires time and verification material")
            if (
                self.status == EvidenceStatus.EXTERNALLY_TIMESTAMPED_VERIFIED
                and self.verifier_id is None
            ):
                raise ValueError("verified external timestamp requires verifier_id")
        else:
            raise ValueError(f"status is not valid for trusted time: {self.status}")
        return self

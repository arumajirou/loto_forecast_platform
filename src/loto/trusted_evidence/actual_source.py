"""Actual-source evidence with distinct publication and fetch times."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from .model_base import (
    SCHEMA_VERSION,
    SHA256_PATTERN,
    MaterialBoundEvidence,
    require_timezone,
)
from .parser_evidence import ParserEvidence
from .signature_evidence import SignatureEvidence
from .source_revision import SourceRevisionEvidence
from .statuses import EvidenceStatus
from .time_evidence import TrustedTimeEvidence


class ActualSourceEvidence(MaterialBoundEvidence):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    evidence_id: str = Field(min_length=1, max_length=256)
    status: EvidenceStatus
    source_name: str | None = Field(default=None, min_length=1, max_length=512)
    source_url: str | None = Field(default=None, min_length=1, max_length=4096)
    raw_bytes_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    raw_bytes_size: int | None = Field(default=None, ge=0)
    headers_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    fetched_at_utc: datetime | None = None
    published_at_utc: datetime | None = None
    normalized_actuals_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    parser: ParserEvidence | None = None
    source_revision: SourceRevisionEvidence | None = None
    publication_time_evidence: TrustedTimeEvidence | None = None
    signature: SignatureEvidence | None = None
    verifier_id: str | None = Field(default=None, min_length=1, max_length=256)
    correction_head_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source_url must be an absolute HTTP or HTTPS URL")
        return value

    @field_validator("fetched_at_utc", "published_at_utc")
    @classmethod
    def validate_source_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_timezone(value, "actual source time")

    @property
    def subject_sha256(self) -> str:
        return str(self.normalized_actuals_sha256 or self.raw_bytes_sha256 or "")

    @model_validator(mode="after")
    def validate_status(self) -> ActualSourceEvidence:
        allowed = {
            EvidenceStatus.NOT_PROVIDED,
            EvidenceStatus.OPERATOR_ASSERTED,
            EvidenceStatus.OFFICIAL_SOURCE_UNVERIFIED,
            EvidenceStatus.OFFICIAL_SOURCE_VERIFIED,
            EvidenceStatus.CORRECTED,
            EvidenceStatus.REVOKED,
        }
        if self.status not in allowed:
            raise ValueError(f"status is not valid for actual source: {self.status}")
        if self.published_at_utc is not None and self.fetched_at_utc is not None:
            if self.published_at_utc > self.fetched_at_utc:
                raise ValueError("actual publication time must not be after fetch time")
        if self.status == EvidenceStatus.NOT_PROVIDED:
            if any(
                value is not None
                for value in (
                    self.source_name,
                    self.source_url,
                    self.raw_bytes_sha256,
                    self.fetched_at_utc,
                )
            ):
                raise ValueError("NOT_PROVIDED actual source must not contain source claims")
            return self
        required = (
            self.source_name,
            self.raw_bytes_sha256,
            self.raw_bytes_size,
            self.fetched_at_utc,
            self.normalized_actuals_sha256,
            self.parser,
        )
        if any(value is None for value in required):
            raise ValueError("actual source requires source, raw bytes, fetch, parser, and output")
        if self.status in {
            EvidenceStatus.OFFICIAL_SOURCE_UNVERIFIED,
            EvidenceStatus.OFFICIAL_SOURCE_VERIFIED,
        }:
            if self.source_url is None or self.headers_sha256 is None:
                raise ValueError("official source evidence requires URL and headers hash")
            material_hashes = {item.sha256 for item in self.verification_materials}
            if self.raw_bytes_sha256 not in material_hashes:
                raise ValueError("official source material must include the raw response bytes")
            if self.headers_sha256 not in material_hashes:
                raise ValueError("official source material must include canonical headers")
        if self.status == EvidenceStatus.OFFICIAL_SOURCE_VERIFIED:
            if self.verifier_id is None or not self.verification_materials:
                raise ValueError("verified official source requires verifier and material")
        if self.status in {EvidenceStatus.CORRECTED, EvidenceStatus.REVOKED}:
            if self.correction_head_sha256 is None:
                raise ValueError("corrected or revoked source requires correction head")
        return self

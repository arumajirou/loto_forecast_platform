"""Strict external-verifier and offline-report result schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .model_base import SCHEMA_VERSION, SHA256_PATTERN, StrictModel
from .statuses import EvidenceStatus, OfflineVerificationStatus, VerificationDomain


class ExternalVerificationResult(StrictModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    verifier_id: str = Field(min_length=1, max_length=256)
    domain: VerificationDomain
    verified: bool
    effective_status: EvidenceStatus
    subject_sha256: str = Field(pattern=SHA256_PATTERN)
    verification_material_sha256: str = Field(pattern=SHA256_PATTERN)
    details_sha256: str = Field(pattern=SHA256_PATTERN)
    failures: list[str] = Field(default_factory=list)


class EvidenceDecision(StrictModel):
    domain: VerificationDomain
    evidence_id: str
    claimed_status: EvidenceStatus
    effective_status: EvidenceStatus
    verifier_id: str | None = None
    material_verified: bool
    externally_verified: bool
    third_party_verifiable: bool
    failures: list[str] = Field(default_factory=list)


class OfflineVerificationReport(StrictModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    status: OfflineVerificationStatus
    bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    integrity_verified: bool
    external_claims_verified: bool
    correction_chain_verified: bool
    decisions: list[EvidenceDecision]
    failures: list[str] = Field(default_factory=list)

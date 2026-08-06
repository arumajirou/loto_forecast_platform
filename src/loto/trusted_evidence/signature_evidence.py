"""Signature evidence schema that prevents HMAC/public-signature confusion."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .model_base import SCHEMA_VERSION, SHA256_PATTERN, MaterialBoundEvidence
from .statuses import EvidenceStatus, PublicVerifiability, SignatureKind


class SignatureEvidence(MaterialBoundEvidence):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    evidence_id: str = Field(min_length=1, max_length=256)
    status: EvidenceStatus
    subject_sha256: str = Field(pattern=SHA256_PATTERN)
    signature_kind: SignatureKind
    algorithm: str | None = Field(default=None, min_length=1, max_length=256)
    signature_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    signer_identity: str | None = Field(default=None, min_length=1, max_length=512)
    key_id: str | None = Field(default=None, min_length=1, max_length=512)
    public_verifiability: PublicVerifiability
    verifier_id: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_status(self) -> SignatureEvidence:
        allowed = {
            EvidenceStatus.NOT_PROVIDED,
            EvidenceStatus.OPERATOR_ASSERTED,
            EvidenceStatus.SIGNATURE_UNVERIFIED,
            EvidenceStatus.SIGNATURE_VERIFIED,
        }
        if self.status not in allowed:
            raise ValueError(f"status is not valid for signature evidence: {self.status}")
        if self.status == EvidenceStatus.NOT_PROVIDED:
            if self.signature_kind != SignatureKind.NONE or self.signature_sha256 is not None:
                raise ValueError("NOT_PROVIDED signature must not contain signature data")
            return self
        if self.signature_kind == SignatureKind.NONE or self.signature_sha256 is None:
            raise ValueError("signature evidence requires kind and signature hash")
        if self.signature_kind == SignatureKind.HMAC:
            if self.public_verifiability != PublicVerifiability.SHARED_SECRET_ONLY:
                raise ValueError("HMAC must be classified as shared-secret-only")
            if self.status == EvidenceStatus.SIGNATURE_VERIFIED:
                raise ValueError("HMAC must not be represented as a public verified signature")
        if self.status == EvidenceStatus.SIGNATURE_VERIFIED:
            if self.signature_kind not in {
                SignatureKind.PUBLIC_KEY,
                SignatureKind.TRANSPARENCY_LOG,
            }:
                raise ValueError("verified public signature requires public verification kind")
            if self.public_verifiability not in {
                PublicVerifiability.PUBLIC_KEY,
                PublicVerifiability.TRANSPARENCY_LOG,
            }:
                raise ValueError("verified signature must be publicly verifiable")
            if self.verifier_id is None or not self.verification_materials:
                raise ValueError("verified signature requires verifier and material")
        return self

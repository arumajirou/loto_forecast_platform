"""Provider interfaces for future external timestamp, signature, and source verifiers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .contracts import (
    ActualSourceEvidence,
    ExternalVerificationResult,
    SignatureEvidence,
    TrustedTimeEvidence,
)


class TrustedTimeVerifier(Protocol):
    verifier_id: str

    def verify(
        self,
        evidence: TrustedTimeEvidence,
        material_root: Path,
    ) -> ExternalVerificationResult: ...


class SignatureVerifier(Protocol):
    verifier_id: str

    def verify(
        self,
        evidence: SignatureEvidence,
        material_root: Path,
    ) -> ExternalVerificationResult: ...


class ActualSourceVerifier(Protocol):
    verifier_id: str

    def verify(
        self,
        evidence: ActualSourceEvidence,
        material_root: Path,
    ) -> ExternalVerificationResult: ...


@dataclass(frozen=True)
class VerifierRegistry:
    trusted_time: dict[str, TrustedTimeVerifier] = field(default_factory=dict)
    signatures: dict[str, SignatureVerifier] = field(default_factory=dict)
    actual_sources: dict[str, ActualSourceVerifier] = field(default_factory=dict)

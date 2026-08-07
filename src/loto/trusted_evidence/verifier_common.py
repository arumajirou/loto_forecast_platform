"""Shared fail-closed checks for injected external-verifier results."""

from __future__ import annotations

from .contracts import ExternalVerificationResult
from .statuses import EvidenceStatus, VerificationDomain


def validate_external_result(
    result: ExternalVerificationResult,
    *,
    verifier_id: str,
    domain: VerificationDomain,
    subject_sha256: str,
    material_sha256: str,
    expected_status: EvidenceStatus,
) -> list[str]:
    failures: list[str] = []
    if result.verifier_id != verifier_id:
        failures.append("external verifier ID does not match the requested verifier")
    if result.domain != domain:
        failures.append("external verifier domain does not match the evidence domain")
    if not result.verified:
        failures.append("external verifier did not verify the evidence")
    if result.effective_status != expected_status:
        failures.append("external verifier returned an unexpected effective status")
    if result.subject_sha256 != subject_sha256:
        failures.append("external verifier subject SHA-256 mismatch")
    if result.verification_material_sha256 != material_sha256:
        failures.append("external verifier material inventory SHA-256 mismatch")
    failures.extend(result.failures)
    return failures

"""Status decisions that preserve local, asserted, and externally verified boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import (
    ActualSourceEvidence,
    EvidenceDecision,
    SignatureEvidence,
    TrustedTimeEvidence,
)
from .interfaces import VerifierRegistry
from .material_verifier import verify_materials
from .statuses import (
    EvidenceStatus,
    PublicVerifiability,
    SignatureKind,
    VerificationDomain,
)
from .verifier_common import validate_external_result


def _external_decision(
    *,
    evidence: Any,
    material_root: Path,
    registry: dict[str, Any],
    domain: VerificationDomain,
    claimed_status: EvidenceStatus,
    verified_status: EvidenceStatus,
    unverified_status: EvidenceStatus,
    label: str,
) -> EvidenceDecision:
    material_failures = verify_materials(
        evidence.verification_materials,
        material_root=material_root,
        label=label,
    )
    failures = list(material_failures)
    verifier_id = evidence.verifier_id
    externally_verified = False
    effective_status = claimed_status
    if claimed_status == verified_status:
        verifier = registry.get(verifier_id or "")
        if verifier is None:
            effective_status = unverified_status
            failures.append("external verifier implementation is unavailable")
        elif material_failures:
            effective_status = unverified_status
        else:
            try:
                result = verifier.verify(evidence, material_root)
            except Exception as exc:
                effective_status = unverified_status
                failures.append(f"external verifier raised: {type(exc).__name__}: {exc}")
            else:
                result_failures = validate_external_result(
                    result,
                    verifier_id=str(verifier_id),
                    domain=domain,
                    subject_sha256=evidence.subject_sha256,
                    material_sha256=str(evidence.verification_material_sha256),
                    expected_status=verified_status,
                )
                failures.extend(result_failures)
                if result_failures:
                    effective_status = unverified_status
                else:
                    externally_verified = True
    return EvidenceDecision(
        domain=domain,
        evidence_id=evidence.evidence_id,
        claimed_status=claimed_status,
        effective_status=effective_status,
        verifier_id=verifier_id,
        material_verified=not material_failures,
        externally_verified=externally_verified,
        third_party_verifiable=externally_verified,
        failures=failures,
    )


def decide_trusted_time(
    evidence: TrustedTimeEvidence,
    *,
    material_root: Path,
    registry: VerifierRegistry,
) -> EvidenceDecision:
    if evidence.status in {
        EvidenceStatus.EXTERNALLY_TIMESTAMPED_VERIFIED,
        EvidenceStatus.EXTERNALLY_TIMESTAMPED_UNVERIFIED,
    }:
        return _external_decision(
            evidence=evidence,
            material_root=material_root,
            registry=registry.trusted_time,
            domain=VerificationDomain.TRUSTED_TIME,
            claimed_status=evidence.status,
            verified_status=EvidenceStatus.EXTERNALLY_TIMESTAMPED_VERIFIED,
            unverified_status=EvidenceStatus.EXTERNALLY_TIMESTAMPED_UNVERIFIED,
            label=f"trusted-time:{evidence.evidence_id}",
        )
    material_failures = verify_materials(
        evidence.verification_materials,
        material_root=material_root,
        label=f"trusted-time:{evidence.evidence_id}",
    )
    boundary_failures = (
        ["local system time is not trusted third-party time"]
        if evidence.status == EvidenceStatus.LOCALLY_TIMESTAMPED
        else []
    )
    return EvidenceDecision(
        domain=VerificationDomain.TRUSTED_TIME,
        evidence_id=evidence.evidence_id,
        claimed_status=evidence.status,
        effective_status=evidence.status,
        verifier_id=None,
        material_verified=not material_failures,
        externally_verified=False,
        third_party_verifiable=False,
        failures=[*material_failures, *boundary_failures],
    )


def decide_signature(
    evidence: SignatureEvidence,
    *,
    material_root: Path,
    registry: VerifierRegistry,
) -> EvidenceDecision:
    if evidence.signature_kind == SignatureKind.HMAC:
        material_failures = verify_materials(
            evidence.verification_materials,
            material_root=material_root,
            label=f"signature:{evidence.evidence_id}",
        )
        return EvidenceDecision(
            domain=VerificationDomain.SIGNATURE,
            evidence_id=evidence.evidence_id,
            claimed_status=evidence.status,
            effective_status=EvidenceStatus.SIGNATURE_UNVERIFIED,
            verifier_id=evidence.verifier_id,
            material_verified=not material_failures,
            externally_verified=False,
            third_party_verifiable=False,
            failures=[
                *material_failures,
                "HMAC is not a third-party public signature",
            ],
        )
    if evidence.status in {
        EvidenceStatus.SIGNATURE_VERIFIED,
        EvidenceStatus.SIGNATURE_UNVERIFIED,
    }:
        decision = _external_decision(
            evidence=evidence,
            material_root=material_root,
            registry=registry.signatures,
            domain=VerificationDomain.SIGNATURE,
            claimed_status=evidence.status,
            verified_status=EvidenceStatus.SIGNATURE_VERIFIED,
            unverified_status=EvidenceStatus.SIGNATURE_UNVERIFIED,
            label=f"signature:{evidence.evidence_id}",
        )
        if evidence.public_verifiability not in {
            PublicVerifiability.PUBLIC_KEY,
            PublicVerifiability.TRANSPARENCY_LOG,
        }:
            return decision.model_copy(
                update={
                    "effective_status": EvidenceStatus.SIGNATURE_UNVERIFIED,
                    "externally_verified": False,
                    "third_party_verifiable": False,
                    "failures": [
                        *decision.failures,
                        "signature is not classified as publicly verifiable",
                    ],
                }
            )
        return decision
    material_failures = verify_materials(
        evidence.verification_materials,
        material_root=material_root,
        label=f"signature:{evidence.evidence_id}",
    )
    return EvidenceDecision(
        domain=VerificationDomain.SIGNATURE,
        evidence_id=evidence.evidence_id,
        claimed_status=evidence.status,
        effective_status=evidence.status,
        verifier_id=None,
        material_verified=not material_failures,
        externally_verified=False,
        third_party_verifiable=False,
        failures=material_failures,
    )


def decide_actual_source(
    evidence: ActualSourceEvidence,
    *,
    material_root: Path,
    registry: VerifierRegistry,
) -> EvidenceDecision:
    if evidence.status in {
        EvidenceStatus.OFFICIAL_SOURCE_VERIFIED,
        EvidenceStatus.OFFICIAL_SOURCE_UNVERIFIED,
    }:
        return _external_decision(
            evidence=evidence,
            material_root=material_root,
            registry=registry.actual_sources,
            domain=VerificationDomain.ACTUAL_SOURCE,
            claimed_status=evidence.status,
            verified_status=EvidenceStatus.OFFICIAL_SOURCE_VERIFIED,
            unverified_status=EvidenceStatus.OFFICIAL_SOURCE_UNVERIFIED,
            label=f"actual-source:{evidence.evidence_id}",
        )
    material_failures = verify_materials(
        evidence.verification_materials,
        material_root=material_root,
        label=f"actual-source:{evidence.evidence_id}",
    )
    return EvidenceDecision(
        domain=VerificationDomain.ACTUAL_SOURCE,
        evidence_id=evidence.evidence_id,
        claimed_status=evidence.status,
        effective_status=evidence.status,
        verifier_id=None,
        material_verified=not material_failures,
        externally_verified=False,
        third_party_verifiable=False,
        failures=material_failures,
    )

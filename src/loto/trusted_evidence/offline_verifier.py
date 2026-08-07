"""Read-only offline verification for trusted-time and actual-source evidence bundles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import EvidenceDecision, OfflineVerificationReport, ThirdPartyEvidenceBundle
from .corrections import verify_correction_chain
from .evidence_decisions import decide_actual_source, decide_signature, decide_trusted_time
from .interfaces import VerifierRegistry
from .material_verifier import verify_materials
from .statuses import EvidenceStatus, OfflineVerificationStatus


def _nested_material_failures(
    bundle: ThirdPartyEvidenceBundle,
    *,
    material_root: Path,
) -> list[str]:
    source = bundle.actual_source
    if source is None:
        return []
    failures: list[str] = []
    if source.source_revision is not None:
        failures.extend(
            verify_materials(
                source.source_revision.verification_materials,
                material_root=material_root,
                label=f"source-revision:{source.source_revision.evidence_id}",
            )
        )
    if source.publication_time_evidence is not None:
        failures.extend(
            verify_materials(
                source.publication_time_evidence.verification_materials,
                material_root=material_root,
                label=(
                    "source-publication-time:"
                    f"{source.publication_time_evidence.evidence_id}"
                ),
            )
        )
    if source.signature is not None:
        failures.extend(
            verify_materials(
                source.signature.verification_materials,
                material_root=material_root,
                label=f"source-signature:{source.signature.evidence_id}",
            )
        )
    return failures


def _correction_failures(bundle: ThirdPartyEvidenceBundle) -> list[str]:
    failures = verify_correction_chain(bundle.corrections)
    source = bundle.actual_source
    if source is not None and source.status in {
        EvidenceStatus.CORRECTED,
        EvidenceStatus.REVOKED,
    }:
        if not bundle.corrections:
            failures.append("corrected or revoked actual source has no correction chain")
        elif source.correction_head_sha256 != bundle.corrections[-1].record_sha256:
            failures.append("actual source correction head does not match correction chain")
    return failures


def verify_evidence_bundle(
    bundle: ThirdPartyEvidenceBundle,
    *,
    material_root: Path,
    registry: VerifierRegistry | None = None,
) -> OfflineVerificationReport:
    """Verify retained material and injected verifier results without network access."""

    registry = registry or VerifierRegistry()
    decisions: list[EvidenceDecision] = []
    for evidence in bundle.trusted_time:
        decisions.append(
            decide_trusted_time(evidence, material_root=material_root, registry=registry)
        )
    for evidence in bundle.signatures:
        decisions.append(
            decide_signature(evidence, material_root=material_root, registry=registry)
        )
    if bundle.actual_source is not None:
        decisions.append(
            decide_actual_source(
                bundle.actual_source,
                material_root=material_root,
                registry=registry,
            )
        )

    failures = [item for decision in decisions for item in decision.failures]
    nested_failures = _nested_material_failures(bundle, material_root=material_root)
    failures.extend(nested_failures)
    correction_failures = _correction_failures(bundle)
    failures.extend(correction_failures)

    material_failed = any(not decision.material_verified for decision in decisions)
    integrity_verified = not material_failed and not nested_failures
    correction_chain_verified = not correction_failures

    claimed_external = [
        decision
        for decision in decisions
        if decision.claimed_status
        in {
            EvidenceStatus.EXTERNALLY_TIMESTAMPED_VERIFIED,
            EvidenceStatus.SIGNATURE_VERIFIED,
            EvidenceStatus.OFFICIAL_SOURCE_VERIFIED,
        }
    ]
    externally_verified = [decision for decision in decisions if decision.externally_verified]
    external_claims_verified = bool(externally_verified) and all(
        decision.externally_verified for decision in claimed_external
    )

    terminal_revoked = bool(bundle.corrections) and (
        bundle.corrections[-1].status == EvidenceStatus.REVOKED
    )
    source_revoked = (
        bundle.actual_source is not None
        and bundle.actual_source.status == EvidenceStatus.REVOKED
    )
    if not integrity_verified or not correction_chain_verified:
        status = OfflineVerificationStatus.FAILED
    elif terminal_revoked or source_revoked:
        status = OfflineVerificationStatus.REVOKED
    elif external_claims_verified:
        status = OfflineVerificationStatus.VERIFIED
    else:
        status = OfflineVerificationStatus.UNVERIFIED

    return OfflineVerificationReport(
        status=status,
        bundle_sha256=bundle.bundle_sha256,
        integrity_verified=integrity_verified,
        external_claims_verified=external_claims_verified,
        correction_chain_verified=correction_chain_verified,
        decisions=decisions,
        failures=failures,
    )


def report_as_dict(report: OfflineVerificationReport) -> dict[str, Any]:
    return report.model_dump(mode="json")

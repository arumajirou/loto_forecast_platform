from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from loto.trusted_evidence import (
    ActualSourceEvidence,
    CorrectionEvidence,
    EvidenceStatus,
    ExternalVerificationResult,
    OfflineVerificationStatus,
    ParserEvidence,
    PublicVerifiability,
    RevisionKind,
    SignatureEvidence,
    SignatureKind,
    SourceRevisionEvidence,
    ThirdPartyEvidenceBundle,
    TimestampAuthority,
    TrustedTimeEvidence,
    VerificationDomain,
    VerificationMaterial,
    VerifierRegistry,
    canonical_sha256,
    headers_sha256,
    legacy_bundle,
    material_inventory_sha256,
    sha256_file,
    verify_correction_chain,
    verify_evidence_bundle,
)

ZERO = "0" * 64
ONE = "1" * 64
TWO = "2" * 64
THREE = "3" * 64
NOW = datetime(2026, 8, 6, 5, 0, tzinfo=UTC)


def _material(
    root: Path,
    name: str = "proof.bin",
    payload: bytes = b"proof",
) -> VerificationMaterial:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return VerificationMaterial(
        material_id=name,
        relative_path=name,
        sha256=sha256_file(path),
        size_bytes=len(payload),
        media_type="application/octet-stream",
        role="verification-proof",
    )


def _material_digest(materials: list[VerificationMaterial]) -> str:
    return material_inventory_sha256([item.model_dump(mode="json") for item in materials])


def _parser(raw_sha256: str = TWO) -> ParserEvidence:
    return ParserEvidence(
        evidence_id="parser-1",
        status=EvidenceStatus.OPERATOR_ASSERTED,
        parser_name="official-results-json",
        parser_version="1.2.3",
        parser_code_sha256=ONE,
        source_format="application/json",
        input_raw_bytes_sha256=raw_sha256,
        output_payload_sha256=THREE,
        parsed_at_utc=NOW,
    )


def _source_revision(root: Path, *, verified: bool = False) -> SourceRevisionEvidence:
    material = _material(root, "revision.proof", b"revision")
    value = 'W/"draw-123"'
    return SourceRevisionEvidence(
        evidence_id="revision-1",
        status=(
            EvidenceStatus.OFFICIAL_SOURCE_VERIFIED
            if verified
            else EvidenceStatus.OFFICIAL_SOURCE_UNVERIFIED
        ),
        revision_kind=RevisionKind.ETAG,
        revision_value=value,
        revision_value_sha256=canonical_sha256(value),
        observed_at_utc=NOW,
        verifier_id="fixture-source" if verified else None,
        verification_materials=[material],
        verification_material_sha256=_material_digest([material]),
    )


def _actual_source(root: Path, *, verified: bool = False) -> ActualSourceEvidence:
    raw_material = _material(root, "actual-source.raw", b"source")
    header_material = _material(
        root,
        "actual-source.headers.json",
        b'{"content-type":"application/json"}',
    )
    materials = [raw_material, header_material]
    return ActualSourceEvidence(
        evidence_id="actual-source-1",
        status=(
            EvidenceStatus.OFFICIAL_SOURCE_VERIFIED
            if verified
            else EvidenceStatus.OFFICIAL_SOURCE_UNVERIFIED
        ),
        source_name="Official Lottery Results",
        source_url="https://official.example/results/123",
        raw_bytes_sha256=raw_material.sha256,
        raw_bytes_size=raw_material.size_bytes,
        headers_sha256=header_material.sha256,
        fetched_at_utc=NOW + timedelta(minutes=2),
        published_at_utc=NOW,
        normalized_actuals_sha256=ONE,
        parser=_parser(raw_material.sha256),
        source_revision=_source_revision(root, verified=False),
        publication_time_evidence=None,
        signature=None,
        verifier_id="fixture-source" if verified else None,
        correction_head_sha256=None,
        verification_materials=materials,
        verification_material_sha256=_material_digest(materials),
    )


def _bundle(
    *,
    trusted_time: list[TrustedTimeEvidence] | None = None,
    signatures: list[SignatureEvidence] | None = None,
    actual_source: ActualSourceEvidence | None = None,
    corrections: list[CorrectionEvidence] | None = None,
) -> ThirdPartyEvidenceBundle:
    return ThirdPartyEvidenceBundle.create(
        bundle_id="bundle-1",
        prediction_lock_sha256=ZERO,
        verification_seal_sha256=ONE,
        actuals_lock_sha256=TWO if actual_source is not None else None,
        created_at_utc=NOW,
        trusted_time=trusted_time or [],
        signatures=signatures or [],
        actual_source=actual_source,
        corrections=corrections or [],
    )


def test_required_status_inventory() -> None:
    expected = {
        "NOT_PROVIDED",
        "OPERATOR_ASSERTED",
        "LOCALLY_TIMESTAMPED",
        "EXTERNALLY_TIMESTAMPED_UNVERIFIED",
        "EXTERNALLY_TIMESTAMPED_VERIFIED",
        "SIGNATURE_UNVERIFIED",
        "SIGNATURE_VERIFIED",
        "OFFICIAL_SOURCE_UNVERIFIED",
        "OFFICIAL_SOURCE_VERIFIED",
        "CORRECTED",
        "REVOKED",
    }
    assert {item.value for item in EvidenceStatus} == expected


def test_strict_unknown_field_and_type_rejection() -> None:
    with pytest.raises(ValidationError):
        TrustedTimeEvidence(
            evidence_id="local",
            status=EvidenceStatus.LOCALLY_TIMESTAMPED,
            subject_sha256=ZERO,
            claimed_time_utc=NOW,
            recorded_at_utc=NOW,
            authority=TimestampAuthority.LOCAL_SYSTEM,
            verification_materials=[],
            verification_material_sha256=None,
            unexpected=True,
        )
    with pytest.raises(ValidationError):
        VerificationMaterial(
            material_id="x",
            relative_path="x",
            sha256=ZERO,
            size_bytes="1",
            media_type="text/plain",
            role="proof",
        )


def test_local_system_time_is_not_trusted_time(tmp_path: Path) -> None:
    evidence = TrustedTimeEvidence(
        evidence_id="local-clock",
        status=EvidenceStatus.LOCALLY_TIMESTAMPED,
        subject_sha256=ZERO,
        claimed_time_utc=NOW,
        recorded_at_utc=NOW,
        authority=TimestampAuthority.LOCAL_SYSTEM,
        verification_materials=[],
        verification_material_sha256=None,
    )
    report = verify_evidence_bundle(_bundle(trusted_time=[evidence]), material_root=tmp_path)
    assert report.status == OfflineVerificationStatus.UNVERIFIED
    decision = report.decisions[0]
    assert decision.effective_status == EvidenceStatus.LOCALLY_TIMESTAMPED
    assert decision.externally_verified is False
    assert decision.third_party_verifiable is False


def test_external_timestamp_without_verifier_downgrades_to_unverified(tmp_path: Path) -> None:
    material = _material(tmp_path, "tsa.tsr", b"timestamp-token")
    evidence = TrustedTimeEvidence(
        evidence_id="tsa-1",
        status=EvidenceStatus.EXTERNALLY_TIMESTAMPED_VERIFIED,
        subject_sha256=ZERO,
        claimed_time_utc=NOW,
        recorded_at_utc=NOW,
        authority=TimestampAuthority.RFC3161_TSA,
        authority_name="Fixture TSA",
        verifier_id="fixture-tsa",
        verification_materials=[material],
        verification_material_sha256=_material_digest([material]),
    )
    report = verify_evidence_bundle(_bundle(trusted_time=[evidence]), material_root=tmp_path)
    assert report.status == OfflineVerificationStatus.UNVERIFIED
    assert report.decisions[0].effective_status == (
        EvidenceStatus.EXTERNALLY_TIMESTAMPED_UNVERIFIED
    )
    assert "external verifier implementation is unavailable" in report.decisions[0].failures


class _FixtureVerifier:
    def __init__(
        self,
        *,
        verifier_id: str,
        domain: VerificationDomain,
        effective_status: EvidenceStatus,
    ) -> None:
        self.verifier_id = verifier_id
        self.domain = domain
        self.effective_status = effective_status

    def verify(self, evidence: Any, material_root: Path) -> ExternalVerificationResult:
        del material_root
        return ExternalVerificationResult(
            verifier_id=self.verifier_id,
            domain=self.domain,
            verified=True,
            effective_status=self.effective_status,
            subject_sha256=evidence.subject_sha256,
            verification_material_sha256=evidence.verification_material_sha256,
            details_sha256=THREE,
            failures=[],
        )


def test_injected_offline_timestamp_verifier_can_verify_material(tmp_path: Path) -> None:
    material = _material(tmp_path, "tsa.tsr", b"timestamp-token")
    evidence = TrustedTimeEvidence(
        evidence_id="tsa-1",
        status=EvidenceStatus.EXTERNALLY_TIMESTAMPED_VERIFIED,
        subject_sha256=ZERO,
        claimed_time_utc=NOW,
        recorded_at_utc=NOW,
        authority=TimestampAuthority.RFC3161_TSA,
        authority_name="Fixture TSA",
        verifier_id="fixture-tsa",
        verification_materials=[material],
        verification_material_sha256=_material_digest([material]),
    )
    registry = VerifierRegistry(
        trusted_time={
            "fixture-tsa": _FixtureVerifier(
                verifier_id="fixture-tsa",
                domain=VerificationDomain.TRUSTED_TIME,
                effective_status=EvidenceStatus.EXTERNALLY_TIMESTAMPED_VERIFIED,
            )
        }
    )
    report = verify_evidence_bundle(
        _bundle(trusted_time=[evidence]),
        material_root=tmp_path,
        registry=registry,
    )
    assert report.status == OfflineVerificationStatus.VERIFIED
    assert report.external_claims_verified is True
    assert report.decisions[0].third_party_verifiable is True


def test_verification_material_tamper_fails_integrity(tmp_path: Path) -> None:
    material = _material(tmp_path, "tsa.tsr", b"timestamp-token")
    evidence = TrustedTimeEvidence(
        evidence_id="tsa-1",
        status=EvidenceStatus.EXTERNALLY_TIMESTAMPED_UNVERIFIED,
        subject_sha256=ZERO,
        claimed_time_utc=NOW,
        recorded_at_utc=NOW,
        authority=TimestampAuthority.RFC3161_TSA,
        authority_name="Fixture TSA",
        verifier_id=None,
        verification_materials=[material],
        verification_material_sha256=_material_digest([material]),
    )
    (tmp_path / "tsa.tsr").write_bytes(b"tampered")
    report = verify_evidence_bundle(_bundle(trusted_time=[evidence]), material_root=tmp_path)
    assert report.status == OfflineVerificationStatus.FAILED
    assert report.integrity_verified is False
    assert any("SHA-256 mismatch" in item for item in report.failures)


def test_hmac_cannot_be_claimed_as_public_verified_signature() -> None:
    with pytest.raises(ValidationError, match="HMAC"):
        SignatureEvidence(
            evidence_id="hmac-1",
            status=EvidenceStatus.SIGNATURE_VERIFIED,
            subject_sha256=ZERO,
            signature_kind=SignatureKind.HMAC,
            algorithm="HMAC-SHA256",
            signature_sha256=ONE,
            signer_identity="operator",
            key_id="shared-secret-1",
            public_verifiability=PublicVerifiability.SHARED_SECRET_ONLY,
            verifier_id="hmac-checker",
            verification_materials=[],
            verification_material_sha256=None,
        )


def test_hmac_remains_unverified_and_not_public(tmp_path: Path) -> None:
    signature = SignatureEvidence(
        evidence_id="hmac-1",
        status=EvidenceStatus.SIGNATURE_UNVERIFIED,
        subject_sha256=ZERO,
        signature_kind=SignatureKind.HMAC,
        algorithm="HMAC-SHA256",
        signature_sha256=ONE,
        signer_identity="operator",
        key_id="shared-secret-1",
        public_verifiability=PublicVerifiability.SHARED_SECRET_ONLY,
        verifier_id=None,
        verification_materials=[],
        verification_material_sha256=None,
    )
    report = verify_evidence_bundle(_bundle(signatures=[signature]), material_root=tmp_path)
    decision = report.decisions[0]
    assert decision.effective_status == EvidenceStatus.SIGNATURE_UNVERIFIED
    assert decision.third_party_verifiable is False
    assert "HMAC is not a third-party public signature" in decision.failures


def test_public_signature_without_verifier_is_fail_closed(tmp_path: Path) -> None:
    material = _material(tmp_path, "signature.sig", b"signature")
    signature = SignatureEvidence(
        evidence_id="sig-1",
        status=EvidenceStatus.SIGNATURE_VERIFIED,
        subject_sha256=ZERO,
        signature_kind=SignatureKind.PUBLIC_KEY,
        algorithm="ed25519",
        signature_sha256=ONE,
        signer_identity="official-source",
        key_id="key-2026",
        public_verifiability=PublicVerifiability.PUBLIC_KEY,
        verifier_id="fixture-signature",
        verification_materials=[material],
        verification_material_sha256=_material_digest([material]),
    )
    report = verify_evidence_bundle(_bundle(signatures=[signature]), material_root=tmp_path)
    assert report.status == OfflineVerificationStatus.UNVERIFIED
    assert report.decisions[0].effective_status == EvidenceStatus.SIGNATURE_UNVERIFIED


def test_actual_source_retains_url_raw_headers_parser_and_revision(tmp_path: Path) -> None:
    source = _actual_source(tmp_path, verified=False)
    assert source.source_url == "https://official.example/results/123"
    assert source.raw_bytes_sha256 == sha256_file(tmp_path / "actual-source.raw")
    assert source.headers_sha256 == sha256_file(tmp_path / "actual-source.headers.json")
    assert source.parser is not None
    assert source.parser.parser_version == "1.2.3"
    assert source.source_revision is not None
    assert source.source_revision.revision_kind == RevisionKind.ETAG
    assert source.published_at_utc == NOW
    assert source.fetched_at_utc == NOW + timedelta(minutes=2)


def test_publication_time_and_fetch_time_are_distinct_and_ordered(tmp_path: Path) -> None:
    source = _actual_source(tmp_path, verified=False)
    assert source.published_at_utc != source.fetched_at_utc
    payload = source.model_dump(mode="python")
    payload["published_at_utc"] = NOW + timedelta(minutes=3)
    with pytest.raises(ValidationError, match="publication time"):
        ActualSourceEvidence.model_validate(payload)


def test_official_source_verified_without_verifier_downgrades(tmp_path: Path) -> None:
    source = _actual_source(tmp_path, verified=True)
    report = verify_evidence_bundle(_bundle(actual_source=source), material_root=tmp_path)
    assert report.status == OfflineVerificationStatus.UNVERIFIED
    assert report.decisions[0].effective_status == EvidenceStatus.OFFICIAL_SOURCE_UNVERIFIED


def test_injected_official_source_verifier_can_verify(tmp_path: Path) -> None:
    source = _actual_source(tmp_path, verified=True)
    registry = VerifierRegistry(
        actual_sources={
            "fixture-source": _FixtureVerifier(
                verifier_id="fixture-source",
                domain=VerificationDomain.ACTUAL_SOURCE,
                effective_status=EvidenceStatus.OFFICIAL_SOURCE_VERIFIED,
            )
        }
    )
    report = verify_evidence_bundle(
        _bundle(actual_source=source),
        material_root=tmp_path,
        registry=registry,
    )
    assert report.status == OfflineVerificationStatus.VERIFIED
    assert report.decisions[0].effective_status == EvidenceStatus.OFFICIAL_SOURCE_VERIFIED


def test_headers_hash_is_order_and_case_stable() -> None:
    first = headers_sha256({"ETag": 'W/"123"', "Content-Type": "application/json"})
    second = headers_sha256({"content-type": "application/json", "etag": 'W/"123"'})
    assert first == second


def test_source_revision_hash_is_bound() -> None:
    value = 'W/"draw-123"'
    with pytest.raises(ValidationError, match="source revision value"):
        SourceRevisionEvidence(
            evidence_id="revision",
            status=EvidenceStatus.OPERATOR_ASSERTED,
            revision_kind=RevisionKind.ETAG,
            revision_value=value,
            revision_value_sha256=ZERO,
            observed_at_utc=NOW,
            verifier_id=None,
            verification_materials=[],
            verification_material_sha256=None,
        )


def test_correction_chain_is_append_only() -> None:
    first = CorrectionEvidence.create(
        correction_id="correction-1",
        sequence_number=1,
        status=EvidenceStatus.CORRECTED,
        subject_evidence_sha256=ZERO,
        previous_correction_sha256=None,
        replacement_evidence_sha256=ONE,
        reason="official source corrected one value",
        actor="operator-a",
        recorded_at_utc=NOW,
    )
    second = CorrectionEvidence.create(
        correction_id="correction-2",
        sequence_number=2,
        status=EvidenceStatus.CORRECTED,
        subject_evidence_sha256=ZERO,
        previous_correction_sha256=first.record_sha256,
        replacement_evidence_sha256=TWO,
        reason="second official correction",
        actor="operator-b",
        recorded_at_utc=NOW + timedelta(minutes=1),
    )
    assert verify_correction_chain([first, second]) == []


def test_correction_chain_rejects_reorder_or_hash_break() -> None:
    first = CorrectionEvidence.create(
        correction_id="correction-1",
        sequence_number=1,
        status=EvidenceStatus.CORRECTED,
        subject_evidence_sha256=ZERO,
        previous_correction_sha256=None,
        replacement_evidence_sha256=ONE,
        reason="first",
        actor="operator-a",
        recorded_at_utc=NOW,
    )
    second = CorrectionEvidence.create(
        correction_id="correction-2",
        sequence_number=2,
        status=EvidenceStatus.CORRECTED,
        subject_evidence_sha256=ZERO,
        previous_correction_sha256=first.record_sha256,
        replacement_evidence_sha256=TWO,
        reason="second",
        actor="operator-b",
        recorded_at_utc=NOW + timedelta(minutes=1),
    )
    failures = verify_correction_chain([second, first])
    assert failures
    assert any("sequence" in item or "previous hash" in item for item in failures)


def test_revoked_correction_makes_bundle_revoked(tmp_path: Path) -> None:
    revoked = CorrectionEvidence.create(
        correction_id="revoke-1",
        sequence_number=1,
        status=EvidenceStatus.REVOKED,
        subject_evidence_sha256=ZERO,
        previous_correction_sha256=None,
        replacement_evidence_sha256=None,
        reason="official source withdrew the result",
        actor="operator-a",
        recorded_at_utc=NOW,
    )
    report = verify_evidence_bundle(_bundle(corrections=[revoked]), material_root=tmp_path)
    assert report.status == OfflineVerificationStatus.REVOKED
    assert report.correction_chain_verified is True


def test_bundle_hash_tamper_is_rejected() -> None:
    bundle = _bundle()
    payload = bundle.model_dump(mode="python")
    payload["prediction_lock_sha256"] = THREE
    with pytest.raises(ValidationError, match="bundle SHA-256"):
        ThirdPartyEvidenceBundle.model_validate(payload)


def test_legacy_local_timestamp_is_preserved_as_local_not_trusted(tmp_path: Path) -> None:
    bundle = legacy_bundle(
        bundle_id="legacy-1",
        prediction_lock={
            "schema_version": "all-auto-prediction-lock-v1",
            "locked_at": NOW.isoformat(),
            "timestamp_authority": "LOCAL_SYSTEM_UTC",
        },
        prediction_lock_sha256=ZERO,
        verification_seal_sha256=ONE,
        actuals_lock=None,
        actuals_lock_sha256=None,
        created_at_utc=NOW,
    )
    assert bundle.trusted_time[0].status == EvidenceStatus.LOCALLY_TIMESTAMPED
    report = verify_evidence_bundle(bundle, material_root=tmp_path)
    assert report.status == OfflineVerificationStatus.UNVERIFIED


def test_legacy_actual_source_remains_operator_asserted(tmp_path: Path) -> None:
    actuals_lock = {
        "schema_version": "all-auto-actuals-lock-v1",
        "ingested_at": NOW.isoformat(),
        "actual_source_label": "operator-verified source",
        "actual_published_at": None,
        "actuals_input": {"sha256": TWO},
        "actuals_normalized_sha256": THREE,
    }
    bundle = legacy_bundle(
        bundle_id="legacy-2",
        prediction_lock={
            "locked_at": NOW.isoformat(),
            "timestamp_authority": "LOCAL_SYSTEM_UTC",
        },
        prediction_lock_sha256=ZERO,
        verification_seal_sha256=ONE,
        actuals_lock=actuals_lock,
        actuals_lock_sha256=TWO,
        created_at_utc=NOW,
    )
    assert bundle.actual_source is not None
    assert bundle.actual_source.status == EvidenceStatus.OPERATOR_ASSERTED
    report = verify_evidence_bundle(bundle, material_root=tmp_path)
    assert report.status == OfflineVerificationStatus.UNVERIFIED


def test_no_network_or_external_crypto_imports_in_foundation() -> None:
    root = Path(__file__).parents[2] / "src/loto/trusted_evidence"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    forbidden = (
        "import requests",
        "import httpx",
        "urllib.request",
        "sigstore",
        "rfc3161",
        "socket.",
    )
    assert not any(token in text for token in forbidden)


def test_operator_asserted_material_tamper_still_fails_integrity(tmp_path: Path) -> None:
    source = _actual_source(tmp_path, verified=False)
    payload = source.model_dump(mode="python")
    payload["status"] = EvidenceStatus.OPERATOR_ASSERTED
    asserted = ActualSourceEvidence.model_validate(payload)
    (tmp_path / "actual-source.raw").write_bytes(b"tampered")
    report = verify_evidence_bundle(_bundle(actual_source=asserted), material_root=tmp_path)
    assert report.status == OfflineVerificationStatus.FAILED
    assert report.integrity_verified is False


class _MismatchedVerifier(_FixtureVerifier):
    def verify(self, evidence: Any, material_root: Path) -> ExternalVerificationResult:
        result = super().verify(evidence, material_root)
        return result.model_copy(update={"subject_sha256": ONE})


def test_external_verifier_identity_mismatch_is_fail_closed(tmp_path: Path) -> None:
    material = _material(tmp_path, "tsa.tsr", b"timestamp-token")
    evidence = TrustedTimeEvidence(
        evidence_id="tsa-identity-mismatch",
        status=EvidenceStatus.EXTERNALLY_TIMESTAMPED_VERIFIED,
        subject_sha256=ZERO,
        claimed_time_utc=NOW,
        recorded_at_utc=NOW,
        authority=TimestampAuthority.RFC3161_TSA,
        authority_name="Fixture TSA",
        verifier_id="fixture-tsa",
        verification_materials=[material],
        verification_material_sha256=_material_digest([material]),
    )
    registry = VerifierRegistry(
        trusted_time={
            "fixture-tsa": _MismatchedVerifier(
                verifier_id="fixture-tsa",
                domain=VerificationDomain.TRUSTED_TIME,
                effective_status=EvidenceStatus.EXTERNALLY_TIMESTAMPED_VERIFIED,
            )
        }
    )
    report = verify_evidence_bundle(
        _bundle(trusted_time=[evidence]),
        material_root=tmp_path,
        registry=registry,
    )
    assert report.status == OfflineVerificationStatus.UNVERIFIED
    assert report.decisions[0].effective_status == (
        EvidenceStatus.EXTERNALLY_TIMESTAMPED_UNVERIFIED
    )
    assert any("subject SHA-256 mismatch" in item for item in report.decisions[0].failures)

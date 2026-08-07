from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from loto.promotion_governance.contracts import (
    ArtifactEvidence,
    BaselineComparisonEvidence,
    EvidenceOrigin,
    EvidenceStatus,
    HoldoutEvidence,
    LicenseEligibility,
    LicenseEligibilityEvidence,
    OOFEvidence,
    PredictionLockEvidence,
    ProspectiveWindowEvidence,
    RuntimeAxis,
    RuntimeCertificationEvidence,
    seal_promotion_subject,
)

H = "a" * 64
H2 = "b" * 64
H3 = "c" * 64
UTC_NOW = datetime(2026, 8, 6, 7, 0, tzinfo=UTC)


def artifact(name: str, status: EvidenceStatus = EvidenceStatus.VERIFIED) -> ArtifactEvidence:
    return ArtifactEvidence(
        evidence_id=name,
        artifact_sha256=H,
        status=status,
        origin=EvidenceOrigin.REAL,
    )


def subject_payload(start: datetime, end: datetime) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "candidate_id": "candidate-1",
        "provider_id": "provider-1",
        "model_repo_id": "org/model",
        "model_revision": "0123456789abcdef",
        "model_artifact_sha256": H,
        "runtime_environment_sha256": H2,
        "code_sha256": H3,
        "config_sha256": H,
        "data_snapshot_sha256": H2,
        "protocol_hash": H3,
        "oof_evidence": OOFEvidence(
            artifact=artifact("oof"),
            protocol_hash=H3,
            fold_count=4,
            seeds=(1, 2, 3),
            seed_mean_hit_at_1=0.4,
            seed_variance_hit_at_1=0.01,
            worst_seed_hit_at_1=0.35,
            worst_fold_hit_at_1=0.30,
        ),
        "holdout_evidence": HoldoutEvidence(
            artifact=artifact("holdout"),
            protocol_hash=H3,
            access_approval_sha256=H2,
            seed_count=3,
        ),
        "prospective_windows": (
            ProspectiveWindowEvidence(
                window_id="window-1",
                candidate_id="candidate-1",
                artifact=artifact("prospective-1"),
                prediction_lock_sha256=H2,
                window_started_at=start,
                window_ended_at=end,
            ),
        ),
        "baseline_comparison": BaselineComparisonEvidence(
            artifact=artifact("baselines"),
            baseline_ids=("random", "fixed", "mean", "median", "last", "frequency", "ar1"),
            candidate_rank=1,
            identical_protocol_confirmed=True,
            all_required_baselines_compared=True,
        ),
        "prediction_lock_evidence": PredictionLockEvidence(
            artifact=artifact("prediction-lock"),
            lock_sha256=H2,
        ),
        "runtime_certification_evidence": RuntimeCertificationEvidence(
            artifact=artifact("runtime"),
            runtime_status=RuntimeAxis.VERIFIED,
            subject_identity_match=True,
            model_load_verified=True,
            input_verified=True,
            inference_verified=True,
            output_shape_verified=True,
            finite_output_verified=True,
            requested_device_verified=True,
            cpu_fallback=False,
        ),
        "license_eligibility": LicenseEligibilityEvidence(
            artifact=artifact("license"),
            eligibility=LicenseEligibility.PRODUCTION_ELIGIBLE,
            production_eligible=True,
        ),
        "first_place_only_selection": False,
        "best_seed_only_selection": False,
        "automatic_retraining": False,
    }


def test_subject_seal_accepts_non_utc_timezone_and_normalizes_hash() -> None:
    jst = timezone(timedelta(hours=9))
    local_start = datetime(2026, 8, 6, 16, 0, tzinfo=jst)
    local_end = datetime(2026, 8, 13, 16, 0, tzinfo=jst)
    local_subject = seal_promotion_subject(subject_payload(local_start, local_end))
    utc_subject = seal_promotion_subject(
        subject_payload(local_start.astimezone(UTC), local_end.astimezone(UTC))
    )
    assert local_subject.subject_sha256 == utc_subject.subject_sha256


def test_verified_holdout_requires_multiple_seeds() -> None:
    with pytest.raises(ValidationError, match="multiple seeds"):
        HoldoutEvidence(
            artifact=artifact("holdout"),
            protocol_hash=H3,
            access_approval_sha256=H2,
            seed_count=1,
        )


def test_unverified_holdout_may_record_single_seed_without_promotion_claim() -> None:
    evidence = HoldoutEvidence(
        artifact=artifact("holdout", EvidenceStatus.UNVERIFIED),
        protocol_hash=H3,
        access_approval_sha256=H2,
        seed_count=1,
    )
    assert evidence.artifact.status is EvidenceStatus.UNVERIFIED


def test_production_license_requires_verified_evidence() -> None:
    with pytest.raises(ValidationError, match="verified evidence"):
        LicenseEligibilityEvidence(
            artifact=artifact("license", EvidenceStatus.UNVERIFIED),
            eligibility=LicenseEligibility.PRODUCTION_ELIGIBLE,
            production_eligible=True,
        )


def test_utc_subject_seal_remains_stable() -> None:
    first = seal_promotion_subject(subject_payload(UTC_NOW, UTC_NOW + timedelta(days=7)))
    second = seal_promotion_subject(subject_payload(UTC_NOW, UTC_NOW + timedelta(days=7)))
    assert first.subject_sha256 == second.subject_sha256

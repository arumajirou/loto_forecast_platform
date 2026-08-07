from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from loto.promotion_governance import (
    AccuracyAxis,
    ActorKind,
    ApprovalScope,
    ArtifactEvidence,
    BaselineComparisonEvidence,
    DeploymentAxis,
    DeploymentEvidence,
    EvidenceOrigin,
    EvidenceStatus,
    HoldoutEvidence,
    HumanApprovalEvidence,
    LegacySource,
    LicenseEligibility,
    LicenseEligibilityEvidence,
    MappingConfidence,
    OOFEvidence,
    PredictionLockEvidence,
    PromotionStatus,
    PromotionTransitionRequest,
    ProspectiveWindowEvidence,
    RegistryAxis,
    RegistryEvidence,
    RuntimeAxis,
    RuntimeCertificationEvidence,
    TransitionContext,
    TransitionIssueCode,
    map_legacy_status,
    seal_promotion_subject,
    validate_transition,
)

H = "a" * 64
H2 = "b" * 64
H3 = "c" * 64
NOW = datetime(2026, 8, 6, 7, 0, tzinfo=UTC)


def artifact(name: str, status: EvidenceStatus = EvidenceStatus.VERIFIED) -> ArtifactEvidence:
    return ArtifactEvidence(
        evidence_id=name,
        artifact_sha256=H,
        status=status,
        origin=EvidenceOrigin.REAL,
    )


def subject_payload(*, prospective: bool = True) -> dict[str, object]:
    windows = ()
    if prospective:
        windows = (
            ProspectiveWindowEvidence(
                window_id="window-1",
                candidate_id="candidate-1",
                artifact=artifact("prospective-1"),
                prediction_lock_sha256=H2,
                window_started_at=NOW,
                window_ended_at=NOW + timedelta(days=7),
            ),
        )
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
        "prospective_windows": windows,
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


def subject(*, prospective: bool = True):
    return seal_promotion_subject(subject_payload(prospective=prospective))


def approval(subject_hash: str, scope: ApprovalScope) -> HumanApprovalEvidence:
    return HumanApprovalEvidence(
        approval_id=f"approval-{scope.value.lower()}",
        scope=scope,
        signed_subject_sha256=subject_hash,
        approval_artifact_sha256=H2,
        approver_ids=("owner", "reviewer"),
        granted_at=NOW,
    )


def context(
    item,
    *,
    registry_axis: RegistryAxis = RegistryAxis.NOT_REGISTERED,
    deployment_axis: DeploymentAxis = DeploymentAxis.NOT_DEPLOYED,
    approval_scope: ApprovalScope | None = None,
) -> TransitionContext:
    registry = RegistryEvidence(
        status=registry_axis,
        subject_sha256=item.subject_sha256,
        registry_receipt_sha256=H if registry_axis is RegistryAxis.REGISTERED else None,
        registry_write_executed=registry_axis is RegistryAxis.REGISTERED,
    )
    deployment = DeploymentEvidence(
        status=deployment_axis,
        shadow_binding_sha256=H if deployment_axis is DeploymentAxis.SHADOW_CANARY else None,
        primary_binding_sha256=H2 if deployment_axis is DeploymentAxis.PRIMARY else None,
        shadow_binding_changed=deployment_axis is DeploymentAxis.SHADOW_CANARY,
        primary_binding_changed=deployment_axis is DeploymentAxis.PRIMARY,
    )
    return TransitionContext(
        runtime_axis=RuntimeAxis.VERIFIED,
        accuracy_axis=AccuracyAxis.VERIFIED_ELIGIBLE,
        registry=registry,
        deployment=deployment,
        human_approval=(
            approval(item.subject_sha256, approval_scope) if approval_scope else None
        ),
    )


def request(item, old: PromotionStatus, new: PromotionStatus, ctx: TransitionContext):
    return PromotionTransitionRequest(
        transition_id=f"{old.value.lower()}-to-{new.value.lower()}",
        subject_sha256=item.subject_sha256,
        from_status=old,
        to_status=new,
        requested_at=NOW,
        actor_kind=ActorKind.SYSTEM,
        context=ctx,
    )


def issue_codes(report) -> set[TransitionIssueCode]:
    return {item.code for item in report.issues}


def test_subject_hash_is_deterministic() -> None:
    first = subject()
    payload = subject_payload()
    reordered = dict(reversed(list(payload.items())))
    second = seal_promotion_subject(reordered)
    assert first.subject_sha256 == second.subject_sha256


def test_subject_hash_changes_with_artifact_identity() -> None:
    first = subject()
    payload = subject_payload()
    payload["model_artifact_sha256"] = H3
    second = seal_promotion_subject(payload)
    assert first.subject_sha256 != second.subject_sha256


def test_subject_hash_changes_with_config_identity() -> None:
    first = subject()
    payload = subject_payload()
    payload["config_sha256"] = H3
    second = seal_promotion_subject(payload)
    assert first.subject_sha256 != second.subject_sha256


def test_wrong_subject_hash_is_rejected() -> None:
    payload = subject_payload()
    with pytest.raises(ValidationError, match="SHA-256 mismatch"):
        from loto.promotion_governance.contracts import PromotionSubject

        PromotionSubject.model_validate({**payload, "subject_sha256": H})


def test_unknown_revision_is_rejected() -> None:
    payload = subject_payload()
    payload["model_revision"] = "UNPINNED"
    with pytest.raises(ValidationError, match="immutable model revision"):
        seal_promotion_subject(payload)


def test_strict_unknown_field_is_rejected() -> None:
    payload = subject_payload()
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        seal_promotion_subject(payload)


def test_automatic_retraining_cannot_be_enabled() -> None:
    payload = subject_payload()
    payload["automatic_retraining"] = True
    with pytest.raises(ValidationError):
        seal_promotion_subject(payload)


def test_best_seed_only_selection_is_rejected() -> None:
    payload = subject_payload()
    payload["best_seed_only_selection"] = True
    with pytest.raises(ValidationError):
        seal_promotion_subject(payload)


def test_first_place_only_selection_is_rejected() -> None:
    payload = subject_payload()
    payload["first_place_only_selection"] = True
    with pytest.raises(ValidationError):
        seal_promotion_subject(payload)


def test_verified_oof_requires_multiple_seeds() -> None:
    payload = subject_payload()
    current = payload["oof_evidence"]
    assert isinstance(current, OOFEvidence)
    with pytest.raises(ValidationError, match="multiple seeds"):
        payload["oof_evidence"] = current.model_copy(update={"seeds": (1,)})
        seal_promotion_subject(payload)


def test_synthetic_runtime_cannot_be_verified() -> None:
    with pytest.raises(ValidationError, match="cannot be VERIFIED"):
        artifact_payload = artifact("runtime").model_dump(mode="python")
        artifact_payload["origin"] = EvidenceOrigin.SYNTHETIC
        ArtifactEvidence.model_validate(artifact_payload)


def test_accuracy_does_not_substitute_for_runtime() -> None:
    item = subject()
    ctx = context(item).model_copy(update={"runtime_axis": RuntimeAxis.UNVERIFIED})
    report = validate_transition(
        item,
        request(item, PromotionStatus.CANDIDATE, PromotionStatus.RUNTIME_VERIFIED, ctx),
    )
    assert not report.allowed
    assert TransitionIssueCode.RUNTIME_AXIS_MISMATCH in issue_codes(report)


def test_illegal_skip_to_primary_is_blocked() -> None:
    item = subject()
    ctx = context(
        item,
        registry_axis=RegistryAxis.REGISTERED,
        deployment_axis=DeploymentAxis.PRIMARY,
        approval_scope=ApprovalScope.PRIMARY_ACTIVATION,
    )
    report = validate_transition(
        item,
        request(item, PromotionStatus.CANDIDATE, PromotionStatus.PRIMARY_ACTIVE, ctx),
    )
    assert not report.allowed
    assert TransitionIssueCode.ILLEGAL_STATUS_EDGE in issue_codes(report)


def test_shadow_eligibility_requires_verified_runtime_axis() -> None:
    item = subject()
    ctx = context(item).model_copy(update={"runtime_axis": RuntimeAxis.UNVERIFIED})
    report = validate_transition(
        item,
        request(
            item,
            PromotionStatus.EVALUATION_PENDING,
            PromotionStatus.SHADOW_ELIGIBLE,
            ctx,
        ),
    )
    assert not report.allowed
    assert TransitionIssueCode.RUNTIME_AXIS_MISMATCH in issue_codes(report)


def test_human_approval_is_required() -> None:
    item = subject()
    ctx = context(item, registry_axis=RegistryAxis.AUTHORIZED)
    report = validate_transition(
        item,
        request(
            item,
            PromotionStatus.HUMAN_REVIEW_REQUIRED,
            PromotionStatus.APPROVED_NOT_REGISTERED,
            ctx,
        ),
    )
    assert TransitionIssueCode.HUMAN_APPROVAL_MISSING in issue_codes(report)


def test_human_approval_cannot_be_automatically_generated() -> None:
    with pytest.raises(ValidationError):
        HumanApprovalEvidence(
            approval_id="approval",
            scope=ApprovalScope.SHADOW_REGISTRATION,
            signed_subject_sha256=H,
            approval_artifact_sha256=H2,
            approver_ids=("owner",),
            granted_at=NOW,
            automatically_generated=True,
        )


def test_registered_not_deployed_is_legal_and_does_not_deploy() -> None:
    item = subject()
    ctx = context(item, registry_axis=RegistryAxis.REGISTERED)
    report = validate_transition(
        item,
        request(
            item,
            PromotionStatus.APPROVED_NOT_REGISTERED,
            PromotionStatus.REGISTERED_NOT_DEPLOYED,
            ctx,
        ),
    )
    assert report.allowed
    assert ctx.deployment.status is DeploymentAxis.NOT_DEPLOYED
    assert not report.deployment_mutation_performed


def test_registry_write_does_not_imply_canary() -> None:
    item = subject()
    ctx = context(item, registry_axis=RegistryAxis.REGISTERED)
    report = validate_transition(
        item,
        request(
            item,
            PromotionStatus.REGISTERED_NOT_DEPLOYED,
            PromotionStatus.SHADOW_CANARY_ACTIVE,
            ctx,
        ),
    )
    assert not report.allowed
    assert TransitionIssueCode.DEPLOYMENT_AXIS_MISMATCH in issue_codes(report)


def test_shadow_canary_does_not_change_primary() -> None:
    with pytest.raises(ValidationError, match="cannot change primary"):
        DeploymentEvidence(
            status=DeploymentAxis.SHADOW_CANARY,
            shadow_binding_sha256=H,
            shadow_binding_changed=True,
            primary_binding_changed=True,
        )


def test_primary_review_requires_prospective_evidence() -> None:
    item = subject(prospective=False)
    ctx = context(
        item,
        registry_axis=RegistryAxis.REGISTERED,
        deployment_axis=DeploymentAxis.SHADOW_CANARY,
    )
    report = validate_transition(
        item,
        request(
            item,
            PromotionStatus.SHADOW_CANARY_ACTIVE,
            PromotionStatus.PRIMARY_REVIEW_ELIGIBLE,
            ctx,
        ),
    )
    assert TransitionIssueCode.PROSPECTIVE_EVIDENCE_MISSING in issue_codes(report)


def test_primary_authorization_requires_primary_scope() -> None:
    item = subject()
    ctx = context(
        item,
        registry_axis=RegistryAxis.REGISTERED,
        deployment_axis=DeploymentAxis.SHADOW_CANARY,
        approval_scope=ApprovalScope.SHADOW_REGISTRATION,
    )
    report = validate_transition(
        item,
        request(
            item,
            PromotionStatus.PRIMARY_REVIEW_ELIGIBLE,
            PromotionStatus.PRIMARY_AUTHORIZED_NOT_EXECUTED,
            ctx,
        ),
    )
    assert TransitionIssueCode.HUMAN_APPROVAL_SCOPE_MISMATCH in issue_codes(report)


def test_primary_active_requires_executed_primary_binding() -> None:
    item = subject()
    ctx = context(
        item,
        registry_axis=RegistryAxis.REGISTERED,
        deployment_axis=DeploymentAxis.SHADOW_CANARY,
        approval_scope=ApprovalScope.PRIMARY_ACTIVATION,
    )
    report = validate_transition(
        item,
        request(
            item,
            PromotionStatus.PRIMARY_AUTHORIZED_NOT_EXECUTED,
            PromotionStatus.PRIMARY_ACTIVE,
            ctx,
        ),
    )
    assert TransitionIssueCode.DEPLOYMENT_AXIS_MISMATCH in issue_codes(report)


def test_primary_active_transition_is_legal_with_all_evidence() -> None:
    item = subject()
    ctx = context(
        item,
        registry_axis=RegistryAxis.REGISTERED,
        deployment_axis=DeploymentAxis.PRIMARY,
        approval_scope=ApprovalScope.PRIMARY_ACTIVATION,
    )
    report = validate_transition(
        item,
        request(
            item,
            PromotionStatus.PRIMARY_AUTHORIZED_NOT_EXECUTED,
            PromotionStatus.PRIMARY_ACTIVE,
            ctx,
        ),
    )
    assert report.allowed
    assert not report.registry_mutation_performed
    assert not report.deployment_mutation_performed


def test_revoked_is_terminal() -> None:
    item = subject()
    ctx = context(item).model_copy(update={"revocation_evidence_sha256": H})
    report = validate_transition(
        item,
        request(item, PromotionStatus.REVOKED, PromotionStatus.CANDIDATE, ctx),
    )
    assert TransitionIssueCode.TERMINAL_STATUS in issue_codes(report)


def test_main_formal_promotion_does_not_bypass_runtime() -> None:
    result = map_legacy_status(LegacySource.MAIN_PROMOTION, "PROMOTE_FORMAL")
    assert result.mapped_status is PromotionStatus.RUNTIME_UNVERIFIED
    assert result.confidence is MappingConfidence.BLOCKED_MISSING_EVIDENCE
    assert not result.human_approval_generated


def test_p7_without_approval_downgrades_to_review() -> None:
    result = map_legacy_status(LegacySource.SKTIME_P7, "APPROVED_NOT_REGISTERED")
    assert result.mapped_status is PromotionStatus.HUMAN_REVIEW_REQUIRED
    assert "verified signed human approval" in result.missing_evidence


def test_p8_with_receipt_maps_exactly_without_deployment() -> None:
    result = map_legacy_status(
        LegacySource.SKTIME_P8,
        "REGISTERED_NOT_DEPLOYED",
        registry_receipt_verified=True,
    )
    assert result.mapped_status is PromotionStatus.REGISTERED_NOT_DEPLOYED
    assert result.confidence is MappingConfidence.EXACT
    assert not result.deployment_mutation_performed


def test_neuralforecast_scoring_never_maps_to_registration() -> None:
    result = map_legacy_status(LegacySource.NEURALFORECAST_SCORING, "FIRST_PLACE")
    assert result.mapped_status is PromotionStatus.EVALUATION_PENDING
    assert not result.registry_mutation_performed


def test_experiment_registry_is_not_production_registry() -> None:
    result = map_legacy_status(
        LegacySource.NEURALFORECAST_EXPERIMENT_REGISTRY,
        "PASS",
        registry_receipt_verified=True,
    )
    assert result.mapped_status is PromotionStatus.EVALUATION_PENDING


def test_transition_subject_mismatch_is_blocked() -> None:
    item = subject()
    req = request(
        item,
        PromotionStatus.CANDIDATE,
        PromotionStatus.RUNTIME_VERIFIED,
        context(item),
    ).model_copy(update={"subject_sha256": H})
    report = validate_transition(item, req)
    assert TransitionIssueCode.SUBJECT_HASH_MISMATCH in issue_codes(report)

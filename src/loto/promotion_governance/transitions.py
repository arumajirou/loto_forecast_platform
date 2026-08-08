"""Pure fail-closed status transition validation with no mutation side effects."""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .contracts import (
    AccuracyAxis,
    ApprovalScope,
    DeploymentAxis,
    EvidenceStatus,
    LicenseEligibility,
    PromotionStatus,
    PromotionSubject,
    PromotionTransitionRequest,
    RegistryAxis,
    RuntimeAxis,
    StrictModel,
)


class TransitionIssueCode(str, Enum):
    SUBJECT_HASH_MISMATCH = "SUBJECT_HASH_MISMATCH"
    ILLEGAL_STATUS_EDGE = "ILLEGAL_STATUS_EDGE"
    TERMINAL_STATUS = "TERMINAL_STATUS"
    RUNTIME_NOT_VERIFIED = "RUNTIME_NOT_VERIFIED"
    RUNTIME_AXIS_MISMATCH = "RUNTIME_AXIS_MISMATCH"
    ACCURACY_NOT_VERIFIED = "ACCURACY_NOT_VERIFIED"
    OOF_NOT_VERIFIED = "OOF_NOT_VERIFIED"
    HOLDOUT_NOT_VERIFIED = "HOLDOUT_NOT_VERIFIED"
    BASELINE_COMPARISON_NOT_VERIFIED = "BASELINE_COMPARISON_NOT_VERIFIED"
    PROTOCOL_MISMATCH = "PROTOCOL_MISMATCH"
    LICENSE_INELIGIBLE = "LICENSE_INELIGIBLE"
    HUMAN_APPROVAL_MISSING = "HUMAN_APPROVAL_MISSING"
    HUMAN_APPROVAL_SCOPE_MISMATCH = "HUMAN_APPROVAL_SCOPE_MISMATCH"
    HUMAN_APPROVAL_SUBJECT_MISMATCH = "HUMAN_APPROVAL_SUBJECT_MISMATCH"
    REGISTRY_SUBJECT_MISMATCH = "REGISTRY_SUBJECT_MISMATCH"
    REGISTRY_NOT_COMMITTED = "REGISTRY_NOT_COMMITTED"
    DEPLOYMENT_AXIS_MISMATCH = "DEPLOYMENT_AXIS_MISMATCH"
    PROSPECTIVE_EVIDENCE_MISSING = "PROSPECTIVE_EVIDENCE_MISSING"
    PROSPECTIVE_EVIDENCE_UNVERIFIED = "PROSPECTIVE_EVIDENCE_UNVERIFIED"
    PREDICTION_LOCK_NOT_VERIFIED = "PREDICTION_LOCK_NOT_VERIFIED"
    BLOCKER_EVIDENCE_MISSING = "BLOCKER_EVIDENCE_MISSING"
    REJECTION_EVIDENCE_MISSING = "REJECTION_EVIDENCE_MISSING"
    REVOCATION_EVIDENCE_MISSING = "REVOCATION_EVIDENCE_MISSING"


class TransitionIssue(StrictModel):
    code: TransitionIssueCode
    detail: str = Field(min_length=1)


class TransitionValidationReport(StrictModel):
    status: str
    allowed: bool
    subject_sha256: str
    from_status: PromotionStatus
    to_status: PromotionStatus
    issues: tuple[TransitionIssue, ...]
    registry_mutation_performed: bool = False
    deployment_mutation_performed: bool = False
    human_approval_generated: bool = False


_ALLOWED: dict[PromotionStatus, frozenset[PromotionStatus]] = {
    PromotionStatus.CANDIDATE: frozenset(
        {
            PromotionStatus.RUNTIME_UNVERIFIED,
            PromotionStatus.RUNTIME_VERIFIED,
            PromotionStatus.BLOCKED,
            PromotionStatus.REJECTED,
        }
    ),
    PromotionStatus.RUNTIME_UNVERIFIED: frozenset(
        {
            PromotionStatus.RUNTIME_VERIFIED,
            PromotionStatus.BLOCKED,
            PromotionStatus.REJECTED,
            PromotionStatus.REVOKED,
        }
    ),
    PromotionStatus.RUNTIME_VERIFIED: frozenset(
        {
            PromotionStatus.EVALUATION_PENDING,
            PromotionStatus.SHADOW_ELIGIBLE,
            PromotionStatus.BLOCKED,
            PromotionStatus.REJECTED,
            PromotionStatus.REVOKED,
        }
    ),
    PromotionStatus.EVALUATION_PENDING: frozenset(
        {
            PromotionStatus.SHADOW_ELIGIBLE,
            PromotionStatus.BLOCKED,
            PromotionStatus.REJECTED,
            PromotionStatus.REVOKED,
        }
    ),
    PromotionStatus.SHADOW_ELIGIBLE: frozenset(
        {
            PromotionStatus.HUMAN_REVIEW_REQUIRED,
            PromotionStatus.BLOCKED,
            PromotionStatus.REJECTED,
            PromotionStatus.REVOKED,
        }
    ),
    PromotionStatus.HUMAN_REVIEW_REQUIRED: frozenset(
        {
            PromotionStatus.APPROVED_NOT_REGISTERED,
            PromotionStatus.BLOCKED,
            PromotionStatus.REJECTED,
            PromotionStatus.REVOKED,
        }
    ),
    PromotionStatus.APPROVED_NOT_REGISTERED: frozenset(
        {
            PromotionStatus.REGISTERED_NOT_DEPLOYED,
            PromotionStatus.BLOCKED,
            PromotionStatus.REJECTED,
            PromotionStatus.REVOKED,
        }
    ),
    PromotionStatus.REGISTERED_NOT_DEPLOYED: frozenset(
        {
            PromotionStatus.SHADOW_CANARY_ACTIVE,
            PromotionStatus.BLOCKED,
            PromotionStatus.REJECTED,
            PromotionStatus.REVOKED,
        }
    ),
    PromotionStatus.SHADOW_CANARY_ACTIVE: frozenset(
        {
            PromotionStatus.PRIMARY_REVIEW_ELIGIBLE,
            PromotionStatus.BLOCKED,
            PromotionStatus.REJECTED,
            PromotionStatus.REVOKED,
        }
    ),
    PromotionStatus.PRIMARY_REVIEW_ELIGIBLE: frozenset(
        {
            PromotionStatus.PRIMARY_AUTHORIZED_NOT_EXECUTED,
            PromotionStatus.BLOCKED,
            PromotionStatus.REJECTED,
            PromotionStatus.REVOKED,
        }
    ),
    PromotionStatus.PRIMARY_AUTHORIZED_NOT_EXECUTED: frozenset(
        {
            PromotionStatus.PRIMARY_ACTIVE,
            PromotionStatus.BLOCKED,
            PromotionStatus.REJECTED,
            PromotionStatus.REVOKED,
        }
    ),
    PromotionStatus.PRIMARY_ACTIVE: frozenset({PromotionStatus.REVOKED}),
    PromotionStatus.BLOCKED: frozenset(),
    PromotionStatus.REJECTED: frozenset(),
    PromotionStatus.REVOKED: frozenset(),
}

_TERMINAL = frozenset({PromotionStatus.BLOCKED, PromotionStatus.REJECTED, PromotionStatus.REVOKED})


def _issue(code: TransitionIssueCode, detail: str) -> TransitionIssue:
    return TransitionIssue(code=code, detail=detail)


def _shadow_evidence_issues(subject: PromotionSubject) -> list[TransitionIssue]:
    issues: list[TransitionIssue] = []
    if subject.runtime_certification_evidence.runtime_status is not RuntimeAxis.VERIFIED:
        issues.append(_issue(TransitionIssueCode.RUNTIME_NOT_VERIFIED, "runtime is not verified"))
    if subject.oof_evidence.artifact.status is not EvidenceStatus.VERIFIED:
        issues.append(_issue(TransitionIssueCode.OOF_NOT_VERIFIED, "OOF evidence is not verified"))
    if subject.holdout_evidence.artifact.status is not EvidenceStatus.VERIFIED:
        issues.append(
            _issue(TransitionIssueCode.HOLDOUT_NOT_VERIFIED, "Holdout evidence is not verified")
        )
    if subject.baseline_comparison.artifact.status is not EvidenceStatus.VERIFIED:
        issues.append(
            _issue(
                TransitionIssueCode.BASELINE_COMPARISON_NOT_VERIFIED,
                "baseline comparison is not verified",
            )
        )
    if not subject.baseline_comparison.identical_protocol_confirmed:
        issues.append(
            _issue(TransitionIssueCode.PROTOCOL_MISMATCH, "baseline protocol is not identical")
        )
    if not subject.baseline_comparison.all_required_baselines_compared:
        issues.append(
            _issue(
                TransitionIssueCode.BASELINE_COMPARISON_NOT_VERIFIED,
                "required baseline inventory is incomplete",
            )
        )
    if subject.license_eligibility.eligibility is not LicenseEligibility.PRODUCTION_ELIGIBLE:
        issues.append(
            _issue(TransitionIssueCode.LICENSE_INELIGIBLE, "license is not production eligible")
        )
    return issues


def _approval_issues(
    subject: PromotionSubject,
    request: PromotionTransitionRequest,
    scope: ApprovalScope,
) -> list[TransitionIssue]:
    approval = request.context.human_approval
    if approval is None:
        return [_issue(TransitionIssueCode.HUMAN_APPROVAL_MISSING, "human approval is required")]
    issues: list[TransitionIssue] = []
    if approval.scope is not scope:
        issues.append(
            _issue(
                TransitionIssueCode.HUMAN_APPROVAL_SCOPE_MISMATCH,
                f"approval scope must be {scope.value}",
            )
        )
    if approval.signed_subject_sha256 != subject.subject_sha256:
        issues.append(
            _issue(
                TransitionIssueCode.HUMAN_APPROVAL_SUBJECT_MISMATCH,
                "approval signs a different subject",
            )
        )
    return issues


def _registered_issues(
    subject: PromotionSubject,
    request: PromotionTransitionRequest,
) -> list[TransitionIssue]:
    registry = request.context.registry
    issues: list[TransitionIssue] = []
    if registry.subject_sha256 != subject.subject_sha256:
        issues.append(
            _issue(
                TransitionIssueCode.REGISTRY_SUBJECT_MISMATCH,
                "registry evidence references a different subject",
            )
        )
    if registry.status is not RegistryAxis.REGISTERED:
        issues.append(
            _issue(TransitionIssueCode.REGISTRY_NOT_COMMITTED, "registry write is not committed")
        )
    return issues


def validate_transition(
    subject: PromotionSubject,
    request: PromotionTransitionRequest,
) -> TransitionValidationReport:
    issues: list[TransitionIssue] = []
    if request.subject_sha256 != subject.subject_sha256:
        issues.append(
            _issue(TransitionIssueCode.SUBJECT_HASH_MISMATCH, "transition changed subject hash")
        )
    if request.from_status in _TERMINAL:
        issues.append(
            _issue(TransitionIssueCode.TERMINAL_STATUS, "terminal status cannot transition")
        )
    elif request.to_status not in _ALLOWED[request.from_status]:
        issues.append(
            _issue(
                TransitionIssueCode.ILLEGAL_STATUS_EDGE,
                f"{request.from_status.value} cannot transition to {request.to_status.value}",
            )
        )

    target = request.to_status
    context = request.context
    if target is PromotionStatus.RUNTIME_VERIFIED:
        if subject.runtime_certification_evidence.runtime_status is not RuntimeAxis.VERIFIED:
            issues.append(
                _issue(TransitionIssueCode.RUNTIME_NOT_VERIFIED, "subject runtime is unverified")
            )
        if context.runtime_axis is not RuntimeAxis.VERIFIED:
            issues.append(
                _issue(TransitionIssueCode.RUNTIME_AXIS_MISMATCH, "runtime axis is not VERIFIED")
            )
    if (
        target
        in {
            PromotionStatus.EVALUATION_PENDING,
            PromotionStatus.SHADOW_ELIGIBLE,
            PromotionStatus.HUMAN_REVIEW_REQUIRED,
            PromotionStatus.APPROVED_NOT_REGISTERED,
            PromotionStatus.REGISTERED_NOT_DEPLOYED,
            PromotionStatus.SHADOW_CANARY_ACTIVE,
            PromotionStatus.PRIMARY_REVIEW_ELIGIBLE,
            PromotionStatus.PRIMARY_AUTHORIZED_NOT_EXECUTED,
            PromotionStatus.PRIMARY_ACTIVE,
        }
        and context.runtime_axis is not RuntimeAxis.VERIFIED
    ):
        issues.append(
            _issue(TransitionIssueCode.RUNTIME_AXIS_MISMATCH, "target requires verified runtime")
        )
    if target in {
        PromotionStatus.SHADOW_ELIGIBLE,
        PromotionStatus.HUMAN_REVIEW_REQUIRED,
        PromotionStatus.APPROVED_NOT_REGISTERED,
        PromotionStatus.REGISTERED_NOT_DEPLOYED,
        PromotionStatus.SHADOW_CANARY_ACTIVE,
        PromotionStatus.PRIMARY_REVIEW_ELIGIBLE,
        PromotionStatus.PRIMARY_AUTHORIZED_NOT_EXECUTED,
        PromotionStatus.PRIMARY_ACTIVE,
    }:
        issues.extend(_shadow_evidence_issues(subject))
        if context.accuracy_axis is not AccuracyAxis.VERIFIED_ELIGIBLE:
            issues.append(
                _issue(
                    TransitionIssueCode.ACCURACY_NOT_VERIFIED,
                    "accuracy axis is not VERIFIED_ELIGIBLE",
                )
            )
    if target is PromotionStatus.APPROVED_NOT_REGISTERED:
        issues.extend(_approval_issues(subject, request, ApprovalScope.SHADOW_REGISTRATION))
        if context.registry.status is not RegistryAxis.AUTHORIZED:
            issues.append(
                _issue(
                    TransitionIssueCode.REGISTRY_NOT_COMMITTED,
                    "registry axis must be AUTHORIZED before registration",
                )
            )
        if context.deployment.status is not DeploymentAxis.NOT_DEPLOYED:
            issues.append(
                _issue(
                    TransitionIssueCode.DEPLOYMENT_AXIS_MISMATCH,
                    "approval must not deploy a subject",
                )
            )
    if target in {
        PromotionStatus.REGISTERED_NOT_DEPLOYED,
        PromotionStatus.SHADOW_CANARY_ACTIVE,
        PromotionStatus.PRIMARY_REVIEW_ELIGIBLE,
        PromotionStatus.PRIMARY_AUTHORIZED_NOT_EXECUTED,
        PromotionStatus.PRIMARY_ACTIVE,
    }:
        issues.extend(_registered_issues(subject, request))
    if target is PromotionStatus.REGISTERED_NOT_DEPLOYED:
        if context.deployment.status is not DeploymentAxis.NOT_DEPLOYED:
            issues.append(
                _issue(
                    TransitionIssueCode.DEPLOYMENT_AXIS_MISMATCH,
                    "registry write must not imply deployment",
                )
            )
    if (
        target
        in {
            PromotionStatus.SHADOW_CANARY_ACTIVE,
            PromotionStatus.PRIMARY_REVIEW_ELIGIBLE,
            PromotionStatus.PRIMARY_AUTHORIZED_NOT_EXECUTED,
        }
        and context.deployment.status is not DeploymentAxis.SHADOW_CANARY
    ):
        issues.append(
            _issue(
                TransitionIssueCode.DEPLOYMENT_AXIS_MISMATCH,
                "target requires a shadow canary and unchanged primary",
            )
        )
    if target in {
        PromotionStatus.PRIMARY_REVIEW_ELIGIBLE,
        PromotionStatus.PRIMARY_AUTHORIZED_NOT_EXECUTED,
        PromotionStatus.PRIMARY_ACTIVE,
    }:
        if not subject.prospective_windows:
            issues.append(
                _issue(
                    TransitionIssueCode.PROSPECTIVE_EVIDENCE_MISSING,
                    "primary review requires prospective windows",
                )
            )
        elif any(
            item.artifact.status is not EvidenceStatus.VERIFIED
            for item in subject.prospective_windows
        ):
            issues.append(
                _issue(
                    TransitionIssueCode.PROSPECTIVE_EVIDENCE_UNVERIFIED,
                    "every prospective window must be verified",
                )
            )
        if subject.prediction_lock_evidence.artifact.status is not EvidenceStatus.VERIFIED:
            issues.append(
                _issue(
                    TransitionIssueCode.PREDICTION_LOCK_NOT_VERIFIED,
                    "prediction lock evidence is not verified",
                )
            )
    if target is PromotionStatus.PRIMARY_AUTHORIZED_NOT_EXECUTED:
        issues.extend(_approval_issues(subject, request, ApprovalScope.PRIMARY_ACTIVATION))
        if context.deployment.primary_binding_changed:
            issues.append(
                _issue(
                    TransitionIssueCode.DEPLOYMENT_AXIS_MISMATCH,
                    "primary authorization must not execute primary change",
                )
            )
    if target is PromotionStatus.PRIMARY_ACTIVE:
        issues.extend(_approval_issues(subject, request, ApprovalScope.PRIMARY_ACTIVATION))
        if context.deployment.status is not DeploymentAxis.PRIMARY:
            issues.append(
                _issue(
                    TransitionIssueCode.DEPLOYMENT_AXIS_MISMATCH,
                    "PRIMARY_ACTIVE requires an executed primary binding",
                )
            )
    if target is PromotionStatus.BLOCKED and context.blocker_evidence_sha256 is None:
        issues.append(
            _issue(TransitionIssueCode.BLOCKER_EVIDENCE_MISSING, "BLOCKED requires evidence")
        )
    if target is PromotionStatus.REJECTED and context.rejection_evidence_sha256 is None:
        issues.append(
            _issue(TransitionIssueCode.REJECTION_EVIDENCE_MISSING, "REJECTED requires evidence")
        )
    if target is PromotionStatus.REVOKED and context.revocation_evidence_sha256 is None:
        issues.append(
            _issue(TransitionIssueCode.REVOCATION_EVIDENCE_MISSING, "REVOKED requires evidence")
        )
    allowed = not issues
    return TransitionValidationReport(
        status="PASS" if allowed else "BLOCKED",
        allowed=allowed,
        subject_sha256=subject.subject_sha256,
        from_status=request.from_status,
        to_status=request.to_status,
        issues=tuple(issues),
    )


def assert_transition_allowed(
    subject: PromotionSubject,
    request: PromotionTransitionRequest,
) -> TransitionValidationReport:
    report = validate_transition(subject, request)
    if not report.allowed:
        detail = "; ".join(f"{item.code.value}: {item.detail}" for item in report.issues)
        raise ValueError(f"promotion transition blocked: {detail}")
    return report

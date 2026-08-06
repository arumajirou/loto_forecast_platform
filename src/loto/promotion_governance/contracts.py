"""Provider-neutral PromotionSubject and lifecycle evidence contracts."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .canonical import canonical_sha256

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
UNKNOWN_REVISIONS = frozenset(
    {"unknown", "unversioned", "unpinned", "latest", "none", "n/a"}
)


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
        allow_inf_nan=False,
    )


class PromotionStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    RUNTIME_UNVERIFIED = "RUNTIME_UNVERIFIED"
    RUNTIME_VERIFIED = "RUNTIME_VERIFIED"
    EVALUATION_PENDING = "EVALUATION_PENDING"
    SHADOW_ELIGIBLE = "SHADOW_ELIGIBLE"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    APPROVED_NOT_REGISTERED = "APPROVED_NOT_REGISTERED"
    REGISTERED_NOT_DEPLOYED = "REGISTERED_NOT_DEPLOYED"
    SHADOW_CANARY_ACTIVE = "SHADOW_CANARY_ACTIVE"
    PRIMARY_REVIEW_ELIGIBLE = "PRIMARY_REVIEW_ELIGIBLE"
    PRIMARY_AUTHORIZED_NOT_EXECUTED = "PRIMARY_AUTHORIZED_NOT_EXECUTED"
    PRIMARY_ACTIVE = "PRIMARY_ACTIVE"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"


class EvidenceStatus(str, Enum):
    NOT_PROVIDED = "NOT_PROVIDED"
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


class EvidenceOrigin(str, Enum):
    REAL = "REAL"
    SYNTHETIC = "SYNTHETIC"
    INJECTED_FAKE = "INJECTED_FAKE"


class RuntimeAxis(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


class AccuracyAxis(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    PENDING = "PENDING"
    VERIFIED_ELIGIBLE = "VERIFIED_ELIGIBLE"
    VERIFIED_INELIGIBLE = "VERIFIED_INELIGIBLE"


class RegistryAxis(str, Enum):
    NOT_REGISTERED = "NOT_REGISTERED"
    AUTHORIZED = "AUTHORIZED"
    REGISTERED = "REGISTERED"


class DeploymentAxis(str, Enum):
    NOT_DEPLOYED = "NOT_DEPLOYED"
    SHADOW_CANARY = "SHADOW_CANARY"
    PRIMARY = "PRIMARY"


class ApprovalScope(str, Enum):
    SHADOW_REGISTRATION = "SHADOW_REGISTRATION"
    PRIMARY_ACTIVATION = "PRIMARY_ACTIVATION"


class ActorKind(str, Enum):
    SYSTEM = "SYSTEM"
    HUMAN = "HUMAN"


class LicenseEligibility(str, Enum):
    UNKNOWN = "UNKNOWN"
    INELIGIBLE = "INELIGIBLE"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    PRODUCTION_ELIGIBLE = "PRODUCTION_ELIGIBLE"


class ArtifactEvidence(StrictModel):
    evidence_id: str = Field(min_length=1, max_length=256)
    artifact_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    status: EvidenceStatus
    origin: EvidenceOrigin

    @field_validator("evidence_id")
    @classmethod
    def validate_evidence_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("unsafe evidence_id")
        return value

    @model_validator(mode="after")
    def verified_requires_real_origin(self) -> "ArtifactEvidence":
        if self.status is EvidenceStatus.VERIFIED and self.origin is not EvidenceOrigin.REAL:
            raise ValueError("synthetic or injected evidence cannot be VERIFIED")
        return self


class OOFEvidence(StrictModel):
    artifact: ArtifactEvidence
    protocol_hash: str = Field(pattern=SHA256_PATTERN.pattern)
    fold_count: int = Field(ge=1)
    seeds: tuple[int, ...] = Field(min_length=1)
    seed_mean_hit_at_1: float = Field(ge=0.0, le=1.0)
    seed_variance_hit_at_1: float = Field(ge=0.0)
    worst_seed_hit_at_1: float = Field(ge=0.0, le=1.0)
    worst_fold_hit_at_1: float = Field(ge=0.0, le=1.0)
    all_seeds_retained: Literal[True] = True
    best_seed_only_selection: Literal[False] = False

    @model_validator(mode="after")
    def validate_seed_inventory(self) -> "OOFEvidence":
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("OOF seeds must be unique")
        if self.artifact.status is EvidenceStatus.VERIFIED and len(self.seeds) < 2:
            raise ValueError("verified OOF promotion evidence requires multiple seeds")
        return self


class HoldoutEvidence(StrictModel):
    artifact: ArtifactEvidence
    protocol_hash: str = Field(pattern=SHA256_PATTERN.pattern)
    access_approval_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    seed_count: int = Field(ge=1)
    best_seed_only_selection: Literal[False] = False

    @model_validator(mode="after")
    def validate_seed_count(self) -> "HoldoutEvidence":
        if self.artifact.status is EvidenceStatus.VERIFIED and self.seed_count < 2:
            raise ValueError("verified Holdout promotion evidence requires multiple seeds")
        return self


class ProspectiveWindowEvidence(StrictModel):
    window_id: str = Field(min_length=1, max_length=256)
    candidate_id: str = Field(min_length=1, max_length=256)
    artifact: ArtifactEvidence
    prediction_lock_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    window_started_at: datetime
    window_ended_at: datetime
    actual_known_at_lock: Literal[False] = False

    @field_validator("window_id", "candidate_id")
    @classmethod
    def validate_safe_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("unsafe prospective identity")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> "ProspectiveWindowEvidence":
        started_offset = self.window_started_at.utcoffset()
        ended_offset = self.window_ended_at.utcoffset()
        if started_offset is None or ended_offset is None:
            raise ValueError("prospective timestamps must be timezone-aware")
        if self.window_ended_at <= self.window_started_at:
            raise ValueError("prospective window end must follow start")
        return self


class BaselineComparisonEvidence(StrictModel):
    artifact: ArtifactEvidence
    baseline_ids: tuple[str, ...] = Field(min_length=1)
    candidate_rank: int = Field(ge=1)
    first_place_only_selection: Literal[False] = False
    identical_protocol_confirmed: bool
    all_required_baselines_compared: bool

    @model_validator(mode="after")
    def validate_baselines(self) -> "BaselineComparisonEvidence":
        if len(set(self.baseline_ids)) != len(self.baseline_ids):
            raise ValueError("baseline IDs must be unique")
        return self


class PredictionLockEvidence(StrictModel):
    artifact: ArtifactEvidence
    lock_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    actual_known_at_lock: Literal[False] = False


class RuntimeCertificationEvidence(StrictModel):
    artifact: ArtifactEvidence
    runtime_status: RuntimeAxis
    subject_identity_match: bool
    model_load_verified: bool
    input_verified: bool
    inference_verified: bool
    output_shape_verified: bool
    finite_output_verified: bool
    requested_device_verified: bool
    cpu_fallback: bool

    @model_validator(mode="after")
    def validate_runtime(self) -> "RuntimeCertificationEvidence":
        checks = (
            self.subject_identity_match,
            self.model_load_verified,
            self.input_verified,
            self.inference_verified,
            self.output_shape_verified,
            self.finite_output_verified,
            self.requested_device_verified,
        )
        if self.runtime_status is RuntimeAxis.VERIFIED:
            if self.artifact.status is not EvidenceStatus.VERIFIED:
                raise ValueError("runtime VERIFIED requires a verified real artifact")
            if not all(checks) or self.cpu_fallback:
                raise ValueError("runtime VERIFIED requires every runtime check and no fallback")
        return self


class LicenseEligibilityEvidence(StrictModel):
    artifact: ArtifactEvidence
    eligibility: LicenseEligibility
    production_eligible: bool
    automatic_license_override: Literal[False] = False

    @model_validator(mode="after")
    def validate_license(self) -> "LicenseEligibilityEvidence":
        expected = self.eligibility is LicenseEligibility.PRODUCTION_ELIGIBLE
        if self.production_eligible != expected:
            raise ValueError("license eligibility and production_eligible disagree")
        if self.production_eligible and self.artifact.status is not EvidenceStatus.VERIFIED:
            raise ValueError("production license eligibility requires verified evidence")
        return self


class PromotionSubject(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    candidate_id: str = Field(min_length=1, max_length=256)
    provider_id: str = Field(min_length=1, max_length=256)
    model_repo_id: str = Field(min_length=1, max_length=256)
    model_revision: str = Field(min_length=1, max_length=256)
    model_artifact_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    runtime_environment_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    code_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    config_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    data_snapshot_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    protocol_hash: str = Field(pattern=SHA256_PATTERN.pattern)
    oof_evidence: OOFEvidence
    holdout_evidence: HoldoutEvidence
    prospective_windows: tuple[ProspectiveWindowEvidence, ...] = ()
    baseline_comparison: BaselineComparisonEvidence
    prediction_lock_evidence: PredictionLockEvidence
    runtime_certification_evidence: RuntimeCertificationEvidence
    license_eligibility: LicenseEligibilityEvidence
    first_place_only_selection: Literal[False] = False
    best_seed_only_selection: Literal[False] = False
    automatic_retraining: Literal[False] = False
    subject_sha256: str = Field(pattern=SHA256_PATTERN.pattern)

    @field_validator("candidate_id", "provider_id", "model_repo_id")
    @classmethod
    def validate_identity(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("unsafe promotion subject identity")
        return value

    @field_validator("model_revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        if value.strip().lower() in UNKNOWN_REVISIONS:
            raise ValueError("promotion subject requires an immutable model revision")
        return value

    @model_validator(mode="after")
    def validate_subject(self) -> "PromotionSubject":
        if self.oof_evidence.protocol_hash != self.protocol_hash:
            raise ValueError("OOF protocol hash differs from subject")
        if self.holdout_evidence.protocol_hash != self.protocol_hash:
            raise ValueError("Holdout protocol hash differs from subject")
        window_ids = [item.window_id for item in self.prospective_windows]
        if len(window_ids) != len(set(window_ids)):
            raise ValueError("prospective window IDs must be unique")
        for window in self.prospective_windows:
            if window.candidate_id != self.candidate_id:
                raise ValueError("prospective window changed candidate identity")
        expected = canonical_sha256(
            self.model_dump(mode="python", exclude={"subject_sha256"})
        )
        if self.subject_sha256 != expected:
            raise ValueError("PromotionSubject SHA-256 mismatch")
        return self


def seal_promotion_subject(payload: dict[str, Any]) -> PromotionSubject:
    if "subject_sha256" in payload:
        raise ValueError("seal_promotion_subject computes subject_sha256")
    subject_sha256 = canonical_sha256(payload)
    return PromotionSubject.model_validate({**payload, "subject_sha256": subject_sha256})


class HumanApprovalEvidence(StrictModel):
    approval_id: str = Field(min_length=1, max_length=256)
    scope: ApprovalScope
    signed_subject_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    approval_artifact_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    approver_ids: tuple[str, ...] = Field(min_length=1)
    granted_at: datetime
    automatically_generated: Literal[False] = False

    @model_validator(mode="after")
    def validate_approval(self) -> "HumanApprovalEvidence":
        if self.granted_at.tzinfo is None or self.granted_at.utcoffset() is None:
            raise ValueError("approval timestamp must be timezone-aware")
        if len(set(self.approver_ids)) != len(self.approver_ids):
            raise ValueError("approval identities must be unique")
        return self


class RegistryEvidence(StrictModel):
    status: RegistryAxis = RegistryAxis.NOT_REGISTERED
    subject_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    registry_receipt_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN.pattern,
    )
    registry_write_executed: bool = False

    @model_validator(mode="after")
    def validate_registry(self) -> "RegistryEvidence":
        if self.status is RegistryAxis.REGISTERED:
            if not self.registry_write_executed or self.registry_receipt_sha256 is None:
                raise ValueError("REGISTERED requires a committed registry receipt")
        elif self.registry_write_executed:
            raise ValueError("registry write cannot execute before REGISTERED")
        return self


class DeploymentEvidence(StrictModel):
    status: DeploymentAxis = DeploymentAxis.NOT_DEPLOYED
    shadow_binding_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN.pattern,
    )
    primary_binding_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN.pattern,
    )
    shadow_binding_changed: bool = False
    primary_binding_changed: bool = False

    @model_validator(mode="after")
    def validate_deployment(self) -> "DeploymentEvidence":
        if self.status is DeploymentAxis.NOT_DEPLOYED:
            if self.shadow_binding_changed or self.primary_binding_changed:
                raise ValueError("NOT_DEPLOYED cannot change a binding")
        if self.status is DeploymentAxis.SHADOW_CANARY:
            if not self.shadow_binding_changed or self.shadow_binding_sha256 is None:
                raise ValueError("SHADOW_CANARY requires shadow binding evidence")
            if self.primary_binding_changed:
                raise ValueError("shadow canary cannot change primary binding")
        if self.status is DeploymentAxis.PRIMARY:
            if not self.primary_binding_changed or self.primary_binding_sha256 is None:
                raise ValueError("PRIMARY requires primary binding evidence")
        return self


class TransitionContext(StrictModel):
    runtime_axis: RuntimeAxis
    accuracy_axis: AccuracyAxis
    registry: RegistryEvidence
    deployment: DeploymentEvidence
    human_approval: HumanApprovalEvidence | None = None
    blocker_evidence_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN.pattern,
    )
    rejection_evidence_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN.pattern,
    )
    revocation_evidence_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN.pattern,
    )
    automatic_retraining: Literal[False] = False


class PromotionTransitionRequest(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    transition_id: str = Field(min_length=1, max_length=256)
    subject_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    from_status: PromotionStatus
    to_status: PromotionStatus
    requested_at: datetime
    actor_kind: ActorKind
    context: TransitionContext

    @field_validator("transition_id")
    @classmethod
    def validate_transition_id(cls, value: str) -> str:
        if not SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("unsafe transition_id")
        return value

    @model_validator(mode="after")
    def validate_timestamp(self) -> "PromotionTransitionRequest":
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("transition timestamp must be timezone-aware")
        return self

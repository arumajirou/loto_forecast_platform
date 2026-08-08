"""Read-only conservative mappings from legacy provider-local promotion statuses."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from .contracts import PromotionStatus, StrictModel


class LegacySource(StrEnum):
    MAIN_PROMOTION = "MAIN_PROMOTION"
    PLATFORM_REGISTRY = "PLATFORM_REGISTRY"
    SKTIME_P6 = "SKTIME_P6"
    SKTIME_P7 = "SKTIME_P7"
    SKTIME_P8 = "SKTIME_P8"
    SKTIME_P9 = "SKTIME_P9"
    SKTIME_P10 = "SKTIME_P10"
    SKTIME_P11 = "SKTIME_P11"
    NEURALFORECAST_PROMOTION_GATE = "NEURALFORECAST_PROMOTION_GATE"
    NEURALFORECAST_SCORING = "NEURALFORECAST_SCORING"
    NEURALFORECAST_EXPERIMENT_REGISTRY = "NEURALFORECAST_EXPERIMENT_REGISTRY"
    PROVIDER_LOCAL = "PROVIDER_LOCAL"


class MappingConfidence(StrEnum):
    EXACT = "EXACT"
    CONSERVATIVE = "CONSERVATIVE"
    BLOCKED_MISSING_EVIDENCE = "BLOCKED_MISSING_EVIDENCE"
    UNKNOWN = "UNKNOWN"


class CompatibilityMappingResult(StrictModel):
    source: LegacySource
    legacy_status: str
    mapped_status: PromotionStatus
    confidence: MappingConfidence
    rationale: str
    missing_evidence: tuple[str, ...] = ()
    mutation_performed: Literal[False] = False
    human_approval_generated: Literal[False] = False
    registry_mutation_performed: Literal[False] = False
    deployment_mutation_performed: Literal[False] = False


def map_legacy_status(
    source: LegacySource,
    legacy_status: str,
    *,
    runtime_verified: bool = False,
    human_approval_verified: bool = False,
    registry_receipt_verified: bool = False,
    shadow_binding_verified: bool = False,
    primary_review_evidence_verified: bool = False,
    primary_approval_verified: bool = False,
    primary_binding_verified: bool = False,
) -> CompatibilityMappingResult:
    key = legacy_status.strip().upper()
    missing: list[str] = []
    confidence = MappingConfidence.CONSERVATIVE
    rationale = "legacy status is mapped without changing any legacy state"

    if source is LegacySource.MAIN_PROMOTION:
        if key in {"PROMOTE_FORMAL", "PROMOTE_PROVISIONAL"}:
            if runtime_verified:
                mapped = PromotionStatus.HUMAN_REVIEW_REQUIRED
                rationale = "accuracy recommendation is review eligibility, not approval"
            else:
                mapped = PromotionStatus.RUNTIME_UNVERIFIED
                missing.append("runtime certification evidence")
                confidence = MappingConfidence.BLOCKED_MISSING_EVIDENCE
        elif key == "CONTINUE_EVALUATION":
            mapped = (
                PromotionStatus.EVALUATION_PENDING
                if runtime_verified
                else PromotionStatus.RUNTIME_UNVERIFIED
            )
        else:
            mapped = PromotionStatus.CANDIDATE
            confidence = MappingConfidence.UNKNOWN
    elif source is LegacySource.SKTIME_P6 and key == "ELIGIBLE_FOR_HUMAN_APPROVAL":
        mapped = PromotionStatus.HUMAN_REVIEW_REQUIRED
        confidence = MappingConfidence.EXACT
    elif source is LegacySource.SKTIME_P7 and key == "APPROVED_NOT_REGISTERED":
        if human_approval_verified:
            mapped = PromotionStatus.APPROVED_NOT_REGISTERED
            confidence = MappingConfidence.EXACT
        else:
            mapped = PromotionStatus.HUMAN_REVIEW_REQUIRED
            missing.append("verified signed human approval")
            confidence = MappingConfidence.BLOCKED_MISSING_EVIDENCE
    elif source is LegacySource.SKTIME_P8 and key == "REGISTERED_NOT_DEPLOYED":
        if registry_receipt_verified:
            mapped = PromotionStatus.REGISTERED_NOT_DEPLOYED
            confidence = MappingConfidence.EXACT
        else:
            mapped = PromotionStatus.APPROVED_NOT_REGISTERED
            missing.append("committed registry receipt")
            confidence = MappingConfidence.BLOCKED_MISSING_EVIDENCE
    elif source is LegacySource.SKTIME_P9 and key == "CANARY_ACTIVE_NOT_PRIMARY":
        if shadow_binding_verified:
            mapped = PromotionStatus.SHADOW_CANARY_ACTIVE
            confidence = MappingConfidence.EXACT
        else:
            mapped = PromotionStatus.REGISTERED_NOT_DEPLOYED
            missing.append("verified shadow binding")
            confidence = MappingConfidence.BLOCKED_MISSING_EVIDENCE
    elif source is LegacySource.SKTIME_P10 and key == "ELIGIBLE_FOR_PRIMARY_PROMOTION_REVIEW":
        if primary_review_evidence_verified:
            mapped = PromotionStatus.PRIMARY_REVIEW_ELIGIBLE
            confidence = MappingConfidence.EXACT
        else:
            mapped = PromotionStatus.SHADOW_CANARY_ACTIVE
            missing.append("verified primary review evidence")
            confidence = MappingConfidence.BLOCKED_MISSING_EVIDENCE
    elif source is LegacySource.SKTIME_P11 and key == "APPROVED_NOT_PRIMARY":
        if primary_approval_verified:
            mapped = PromotionStatus.PRIMARY_AUTHORIZED_NOT_EXECUTED
            confidence = MappingConfidence.EXACT
        else:
            mapped = PromotionStatus.PRIMARY_REVIEW_ELIGIBLE
            missing.append("verified primary activation approval")
            confidence = MappingConfidence.BLOCKED_MISSING_EVIDENCE
    elif source is LegacySource.NEURALFORECAST_PROMOTION_GATE and key == "PASS":
        mapped = (
            PromotionStatus.RUNTIME_VERIFIED
            if runtime_verified
            else PromotionStatus.RUNTIME_UNVERIFIED
        )
        rationale = "pipeline gate PASS is not production approval or deployment"
        if not runtime_verified:
            missing.append("real runtime certification evidence")
    elif source is LegacySource.NEURALFORECAST_SCORING:
        mapped = PromotionStatus.EVALUATION_PENDING
        rationale = "ranking and first place never imply human approval or registration"
    elif source is LegacySource.NEURALFORECAST_EXPERIMENT_REGISTRY and key == "PASS":
        mapped = PromotionStatus.EVALUATION_PENDING
        rationale = "experiment evidence registration is not production model registration"
    elif source is LegacySource.PLATFORM_REGISTRY:
        if primary_binding_verified and primary_approval_verified:
            mapped = PromotionStatus.PRIMARY_ACTIVE
            confidence = MappingConfidence.EXACT
        elif primary_binding_verified:
            mapped = PromotionStatus.PRIMARY_REVIEW_ELIGIBLE
            missing.append("verified primary activation approval")
            confidence = MappingConfidence.BLOCKED_MISSING_EVIDENCE
        elif registry_receipt_verified:
            mapped = PromotionStatus.REGISTERED_NOT_DEPLOYED
            confidence = MappingConfidence.CONSERVATIVE
        else:
            mapped = PromotionStatus.CANDIDATE
            missing.append("registry receipt or explicit deployment binding")
            confidence = MappingConfidence.BLOCKED_MISSING_EVIDENCE
    else:
        mapped = PromotionStatus.CANDIDATE
        confidence = MappingConfidence.UNKNOWN
        rationale = "unknown provider-local status cannot be promoted automatically"

    return CompatibilityMappingResult(
        source=source,
        legacy_status=legacy_status,
        mapped_status=mapped,
        confidence=confidence,
        rationale=rationale,
        missing_evidence=tuple(missing),
    )

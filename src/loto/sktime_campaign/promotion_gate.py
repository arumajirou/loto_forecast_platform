from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


class MetricSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mean: float
    variance: float = Field(ge=0.0)
    worst: float


class CandidateMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hit_at_1: MetricSummary
    all_position_hit_at_1: MetricSummary
    mae: MetricSummary
    mse: MetricSummary
    rmse: MetricSummary


class ProspectiveWindowEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    window_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    monitor_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_lock_seal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    actuals_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_at_utc: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    revealed_at_utc: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    draw_no: list[int] = Field(min_length=1)
    shadow_candidate_id: str = Field(min_length=1)
    integrity_status: Literal["PASS"] = "PASS"
    drift_status: Literal["STABLE", "WARNING", "CRITICAL"]
    recommendation: Literal[
        "CONTINUE_SHADOW",
        "CONTINUE_SHADOW_REVIEW_REQUIRED",
        "BLOCK_PROMOTION_RETRAIN_REVIEW_REQUIRED",
    ]
    automatic_retraining: Literal[False] = False
    automatic_promotion: Literal[False] = False
    promotion_status: Literal["NOT_PROMOTED"] = "NOT_PROMOTED"
    shadow_metrics: CandidateMetrics
    baseline_metrics: dict[str, CandidateMetrics] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_window(self) -> ProspectiveWindowEvidence:
        sealed = _parse_utc(self.sealed_at_utc, label="sealed_at_utc")
        revealed = _parse_utc(self.revealed_at_utc, label="revealed_at_utc")
        if revealed <= sealed:
            raise ValueError("Prospective actual reveal must follow prediction seal")
        if self.draw_no != sorted(self.draw_no):
            raise ValueError("window draw_no must be sorted")
        if len(set(self.draw_no)) != len(self.draw_no):
            raise ValueError("window draw_no must be unique")
        expected_recommendation = {
            "STABLE": "CONTINUE_SHADOW",
            "WARNING": "CONTINUE_SHADOW_REVIEW_REQUIRED",
            "CRITICAL": "BLOCK_PROMOTION_RETRAIN_REVIEW_REQUIRED",
        }[self.drift_status]
        if self.recommendation != expected_recommendation:
            raise ValueError("drift status and recommendation disagree")
        return self


class PromotionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_prospective_windows: int = Field(default=3, ge=1)
    minimum_total_draws: int = Field(default=3, ge=1)
    minimum_weighted_hit_at_1: float = Field(default=0.90, ge=0.0, le=1.0)
    minimum_worst_window_hit_at_1: float = Field(
        default=0.90,
        ge=0.0,
        le=1.0,
    )
    maximum_hit_drop_from_holdout: float = Field(default=0.05, ge=0.0)
    maximum_mae_increase_from_holdout: float = Field(default=0.50, ge=0.0)
    maximum_warning_windows: int = Field(default=0, ge=0)
    maximum_critical_windows: int = Field(default=0, ge=0)
    require_all_baselines_beaten: bool = True


class PromotionGateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["prospective_promotion_gate"] = "prospective_promotion_gate"
    output_dir: str = Field(min_length=1)
    run_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$", min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    shadow_candidate_id: str = Field(min_length=1)
    upstream_artifact_sha256: dict[str, str]
    runtime_certification_status: Literal["PASS"] = "PASS"
    leakage_audit_status: Literal["PASS"] = "PASS"
    data_quality_status: Literal["PASS"] = "PASS"
    seed_policy_status: Literal["PASS"] = "PASS"
    preactual_lock_status: Literal["PASS"] = "PASS"
    holdout_reference_metrics: CandidateMetrics
    windows: list[ProspectiveWindowEvidence] = Field(min_length=1)
    policy: PromotionPolicy = Field(default_factory=PromotionPolicy)
    human_approval_granted: Literal[False] = False

    @model_validator(mode="after")
    def validate_request(self) -> PromotionGateRequest:
        required = {"p0", "p1", "p2", "p3", "p4"}
        if set(self.upstream_artifact_sha256) != required:
            raise ValueError("upstream artifact inventory must be exactly P0-P4")
        for value in self.upstream_artifact_sha256.values():
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError("upstream artifact SHA-256 is invalid")
        window_ids = [item.window_id for item in self.windows]
        if len(window_ids) != len(set(window_ids)):
            raise ValueError("Prospective window IDs must be unique")
        seals = [item.prediction_lock_seal_sha256 for item in self.windows]
        if len(seals) != len(set(seals)):
            raise ValueError("Prospective prediction-lock seals must be unique")
        seen_draws: set[int] = set()
        for window in self.windows:
            if window.shadow_candidate_id != self.shadow_candidate_id:
                raise ValueError("Prospective window changed the shadow candidate")
            overlap = seen_draws.intersection(window.draw_no)
            if overlap:
                raise ValueError("Prospective windows contain overlapping draw IDs")
            seen_draws.update(window.draw_no)
        return self


def _parse_utc(value: str, *, label: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError(f"{label} must use strict UTC Z format") from exc


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _aggregate_metric(
    windows: list[ProspectiveWindowEvidence],
    *,
    metric_name: str,
    baseline_id: str | None = None,
) -> MetricSummary:
    weights = np.asarray([len(item.draw_no) for item in windows], dtype=float)
    summaries: list[MetricSummary] = []
    for item in windows:
        metrics = item.shadow_metrics if baseline_id is None else item.baseline_metrics[baseline_id]
        summaries.append(getattr(metrics, metric_name))
    means = np.asarray([item.mean for item in summaries], dtype=float)
    weighted_mean = float(np.average(means, weights=weights))
    variance = float(np.average(np.square(means - weighted_mean), weights=weights))
    worst = (
        float(min(item.worst for item in summaries))
        if "hit" in metric_name
        else float(max(item.worst for item in summaries))
    )
    return MetricSummary(mean=weighted_mean, variance=variance, worst=worst)


def aggregate_candidate_metrics(
    windows: list[ProspectiveWindowEvidence],
    *,
    baseline_id: str | None = None,
) -> CandidateMetrics:
    return CandidateMetrics(
        **{
            name: _aggregate_metric(
                windows,
                metric_name=name,
                baseline_id=baseline_id,
            )
            for name in (
                "hit_at_1",
                "all_position_hit_at_1",
                "mae",
                "mse",
                "rmse",
            )
        }
    )


def aggregate_all_evidence(
    request: PromotionGateRequest,
) -> dict[str, Any]:
    baseline_ids = sorted(
        set.intersection(*(set(item.baseline_metrics) for item in request.windows))
    )
    return {
        "schema_version": "1.0",
        "shadow_candidate_id": request.shadow_candidate_id,
        "window_count": len(request.windows),
        "total_draw_count": sum(len(item.draw_no) for item in request.windows),
        "stable_window_count": sum(item.drift_status == "STABLE" for item in request.windows),
        "warning_window_count": sum(item.drift_status == "WARNING" for item in request.windows),
        "critical_window_count": sum(item.drift_status == "CRITICAL" for item in request.windows),
        "shadow_metrics": aggregate_candidate_metrics(request.windows).model_dump(),
        "baseline_metrics": {
            baseline_id: aggregate_candidate_metrics(
                request.windows,
                baseline_id=baseline_id,
            ).model_dump()
            for baseline_id in baseline_ids
        },
        "window_ids": [item.window_id for item in request.windows],
        "draw_no": [draw_no for item in request.windows for draw_no in item.draw_no],
    }


def _rule(
    rule_id: str,
    *,
    passed: bool,
    observed: Any,
    threshold: Any,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "passed": passed,
        "observed": observed,
        "threshold": threshold,
    }


def evaluate_rules(
    request: PromotionGateRequest,
    aggregate: dict[str, Any],
) -> list[dict[str, Any]]:
    policy = request.policy
    shadow = CandidateMetrics.model_validate(aggregate["shadow_metrics"])
    holdout = request.holdout_reference_metrics
    hit_drop = holdout.hit_at_1.mean - shadow.hit_at_1.mean
    mae_increase = shadow.mae.mean - holdout.mae.mean
    baseline_checks = []
    for baseline_id, payload in aggregate["baseline_metrics"].items():
        baseline = CandidateMetrics.model_validate(payload)
        baseline_checks.append(
            {
                "baseline_id": baseline_id,
                "hit_at_1_delta": shadow.hit_at_1.mean - baseline.hit_at_1.mean,
                "mae_improvement": baseline.mae.mean - shadow.mae.mean,
                "passed": (
                    shadow.hit_at_1.mean >= baseline.hit_at_1.mean
                    and shadow.mae.mean <= baseline.mae.mean
                ),
            }
        )
    return [
        _rule(
            "MINIMUM_PROSPECTIVE_WINDOWS",
            passed=aggregate["window_count"] >= policy.minimum_prospective_windows,
            observed=aggregate["window_count"],
            threshold=policy.minimum_prospective_windows,
        ),
        _rule(
            "MINIMUM_TOTAL_DRAWS",
            passed=aggregate["total_draw_count"] >= policy.minimum_total_draws,
            observed=aggregate["total_draw_count"],
            threshold=policy.minimum_total_draws,
        ),
        _rule(
            "WARNING_WINDOW_LIMIT",
            passed=(aggregate["warning_window_count"] <= policy.maximum_warning_windows),
            observed=aggregate["warning_window_count"],
            threshold=policy.maximum_warning_windows,
        ),
        _rule(
            "CRITICAL_WINDOW_LIMIT",
            passed=(aggregate["critical_window_count"] <= policy.maximum_critical_windows),
            observed=aggregate["critical_window_count"],
            threshold=policy.maximum_critical_windows,
        ),
        _rule(
            "WEIGHTED_HIT_AT_1_TARGET",
            passed=shadow.hit_at_1.mean >= policy.minimum_weighted_hit_at_1,
            observed=shadow.hit_at_1.mean,
            threshold=policy.minimum_weighted_hit_at_1,
        ),
        _rule(
            "WORST_WINDOW_HIT_AT_1_TARGET",
            passed=(shadow.hit_at_1.worst >= policy.minimum_worst_window_hit_at_1),
            observed=shadow.hit_at_1.worst,
            threshold=policy.minimum_worst_window_hit_at_1,
        ),
        _rule(
            "HOLDOUT_HIT_REGRESSION_LIMIT",
            passed=hit_drop <= policy.maximum_hit_drop_from_holdout,
            observed=hit_drop,
            threshold=policy.maximum_hit_drop_from_holdout,
        ),
        _rule(
            "HOLDOUT_MAE_REGRESSION_LIMIT",
            passed=mae_increase <= policy.maximum_mae_increase_from_holdout,
            observed=mae_increase,
            threshold=policy.maximum_mae_increase_from_holdout,
        ),
        _rule(
            "BEATS_ALL_BASELINES",
            passed=(
                all(item["passed"] for item in baseline_checks)
                if policy.require_all_baselines_beaten
                else True
            ),
            observed=baseline_checks,
            threshold="hit_at_1>=baseline and mae<=baseline",
        ),
    ]


def _decision_from_rules(rules: list[dict[str, Any]]) -> str:
    mapping = {
        "MINIMUM_PROSPECTIVE_WINDOWS": "BLOCKED_INSUFFICIENT_WINDOWS",
        "MINIMUM_TOTAL_DRAWS": "BLOCKED_INSUFFICIENT_DRAWS",
        "WARNING_WINDOW_LIMIT": "BLOCKED_WARNING_DRIFT",
        "CRITICAL_WINDOW_LIMIT": "BLOCKED_CRITICAL_DRIFT",
        "WEIGHTED_HIT_AT_1_TARGET": "BLOCKED_HIT_TARGET",
        "WORST_WINDOW_HIT_AT_1_TARGET": "BLOCKED_WORST_CASE",
        "HOLDOUT_HIT_REGRESSION_LIMIT": "BLOCKED_HOLDOUT_REGRESSION",
        "HOLDOUT_MAE_REGRESSION_LIMIT": "BLOCKED_HOLDOUT_REGRESSION",
        "BEATS_ALL_BASELINES": "BLOCKED_BASELINE_SUPERIORITY",
    }
    first_failed = next((item for item in rules if not item["passed"]), None)
    return (
        "ELIGIBLE_FOR_HUMAN_APPROVAL" if first_failed is None else mapping[first_failed["rule_id"]]
    )


def run_promotion_gate(request: PromotionGateRequest) -> dict[str, Any]:
    aggregate = aggregate_all_evidence(request)
    rules = evaluate_rules(request, aggregate)
    decision = _decision_from_rules(rules)
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "stage": "prospective_promotion_gate",
        "run_id": request.run_id,
        "shadow_candidate_id": request.shadow_candidate_id,
        "aggregated_metrics": aggregate,
        "rule_evaluation": rules,
        "decision": decision,
        "eligible_for_human_approval": (decision == "ELIGIBLE_FOR_HUMAN_APPROVAL"),
        "human_approval_required": True,
        "human_approval_granted": False,
        "automatic_promotion": False,
        "automatic_retraining": False,
        "registry_write_allowed": False,
        "promotion_status": "NOT_PROMOTED",
        "next_action": (
            "HUMAN_REVIEW_REQUIRED"
            if decision == "ELIGIBLE_FOR_HUMAN_APPROVAL"
            else "CONTINUE_SHADOW_AND_COLLECT_EVIDENCE"
        ),
    }

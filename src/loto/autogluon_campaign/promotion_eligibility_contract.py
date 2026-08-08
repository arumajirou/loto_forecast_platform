from __future__ import annotations

import math
import statistics as stats
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loto.autogluon_campaign.holdout_prospective import HoldoutProspectiveError

PROMOTION_SCHEMA = "autogluon-promotion-eligibility-v1"
REQUIRED_BASELINES = (
    "baseline_random",
    "baseline_fixed",
    "baseline_mean",
    "baseline_median",
    "baseline_last",
    "baseline_frequency",
    "baseline_ar1",
)


class PromotionEligibilityError(HoldoutProspectiveError):
    pass


class PromotionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_prospective_windows: int = Field(default=3, ge=1)
    minimum_prospective_draws: int = Field(default=3, ge=1)
    hit_at_1_target: float = Field(default=0.90, ge=0.0, le=1.0)
    maximum_hit_at_1_drop: float = Field(default=0.05, ge=0.0, le=1.0)
    maximum_mae_increase: float = Field(default=0.50, ge=0.0)
    require_all_windows_stable: bool = True
    require_all_baselines_beaten: bool = True
    automatic_promotion: bool = False
    automatic_retraining: bool = False
    registry_write_allowed: bool = False

    @model_validator(mode="after")
    def fail_closed(self) -> "PromotionPolicy":
        if self.automatic_promotion:
            raise ValueError("automatic promotion is forbidden")
        if self.automatic_retraining:
            raise ValueError("automatic retraining is forbidden")
        if self.registry_write_allowed:
            raise ValueError("registry writes are forbidden")
        return self


def require_finite_metric(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise PromotionEligibilityError("METRIC_INVALID", name) from exc
    if not math.isfinite(result):
        raise PromotionEligibilityError("METRIC_NON_FINITE", name)
    return result


def normalize_metric_row(row: Mapping[str, Any]) -> dict[str, Any]:
    candidate_id = str(row.get("candidate_id", "")).strip()
    if not candidate_id:
        raise PromotionEligibilityError("CANDIDATE_ID_MISSING", str(row))
    seed = row.get("seed")
    draw_id = row.get("draw_id")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise PromotionEligibilityError("SEED_INVALID", str(seed))
    if isinstance(draw_id, bool) or not isinstance(draw_id, int):
        raise PromotionEligibilityError("DRAW_ID_INVALID", str(draw_id))
    return {
        "candidate_id": candidate_id,
        "seed": seed,
        "draw_id": draw_id,
        "hit_at_1": require_finite_metric(row.get("hit_at_1"), "hit_at_1"),
        "all_position_hit_at_1": require_finite_metric(
            row.get("all_position_hit_at_1"),
            "all_position_hit_at_1",
        ),
        "mae": require_finite_metric(row.get("mae"), "mae"),
        "mse": require_finite_metric(row.get("mse"), "mse"),
        "rmse": require_finite_metric(row.get("rmse"), "rmse"),
    }


def aggregate_candidate_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int], list[Mapping[str, Any]]] = {}
    for row in rows:
        key = (str(row["candidate_id"]), int(row["seed"]))
        groups.setdefault(key, []).append(row)

    per_seed: list[dict[str, Any]] = []
    for (candidate_id, seed), values in sorted(groups.items()):
        per_seed.append(
            {
                "candidate_id": candidate_id,
                "seed": seed,
                "draw_count": len({int(row["draw_id"]) for row in values}),
                "mean_hit_at_1": stats.fmean(float(row["hit_at_1"]) for row in values),
                "mean_all_position_hit_at_1": stats.fmean(
                    float(row["all_position_hit_at_1"]) for row in values
                ),
                "mean_mae": stats.fmean(float(row["mae"]) for row in values),
                "mean_mse": stats.fmean(float(row["mse"]) for row in values),
                "mean_rmse": stats.fmean(float(row["rmse"]) for row in values),
            }
        )

    candidates: dict[str, list[dict[str, Any]]] = {}
    for row in per_seed:
        candidates.setdefault(str(row["candidate_id"]), []).append(row)

    summaries: list[dict[str, Any]] = []
    for candidate_id, values in sorted(candidates.items()):
        hits = [float(row["mean_hit_at_1"]) for row in values]
        maes = [float(row["mean_mae"]) for row in values]
        summaries.append(
            {
                "candidate_id": candidate_id,
                "seed_count": len(values),
                "draw_count": max(int(row["draw_count"]) for row in values),
                "mean_hit_at_1": stats.fmean(hits),
                "variance_hit_at_1": (stats.pvariance(hits) if len(hits) > 1 else 0.0),
                "worst_seed_hit_at_1": min(hits),
                "mean_all_position_hit_at_1": stats.fmean(
                    float(row["mean_all_position_hit_at_1"]) for row in values
                ),
                "mean_mae": stats.fmean(maes),
                "variance_mae": (stats.pvariance(maes) if len(maes) > 1 else 0.0),
                "worst_seed_mae": max(maes),
                "mean_mse": stats.fmean(float(row["mean_mse"]) for row in values),
                "mean_rmse": stats.fmean(float(row["mean_rmse"]) for row in values),
            }
        )
    return summaries


def validate_window_evidence(window_evidence: Mapping[str, Any]) -> None:
    holdout = window_evidence.get("holdout")
    prospective = window_evidence.get("prospective")
    if not isinstance(holdout, Mapping) or not isinstance(prospective, list):
        raise PromotionEligibilityError("WINDOW_EVIDENCE_INVALID", str(window_evidence))
    if holdout.get("stage") != "holdout":
        raise PromotionEligibilityError("HOLDOUT_STAGE_REQUIRED", str(holdout))
    if not prospective:
        raise PromotionEligibilityError("PROSPECTIVE_EVIDENCE_REQUIRED", "empty")
    if any(not isinstance(window, Mapping) for window in prospective):
        raise PromotionEligibilityError("PROSPECTIVE_WINDOW_INVALID", str(prospective))
    if any(window.get("stage") != "prospective" for window in prospective):
        raise PromotionEligibilityError("PROSPECTIVE_STAGE_REQUIRED", str(prospective))

    candidate_id = str(holdout.get("selected_candidate_id", ""))
    if not candidate_id:
        raise PromotionEligibilityError("SELECTED_CANDIDATE_MISSING", str(holdout))
    if any(window.get("selected_candidate_id") != candidate_id for window in prospective):
        raise PromotionEligibilityError("SHADOW_CANDIDATE_CHANGED", candidate_id)

    windows = [holdout, *prospective]
    run_ids = [str(window.get("source_run_id", "")) for window in windows]
    if any(not run_id for run_id in run_ids) or len(set(run_ids)) != len(run_ids):
        raise PromotionEligibilityError("SOURCE_RUN_ID_INVALID", str(run_ids))

    seen: set[int] = set()
    for window in windows:
        draw_ids = window.get("draw_ids")
        if not isinstance(draw_ids, list) or not draw_ids:
            raise PromotionEligibilityError("WINDOW_DRAW_IDS_INVALID", str(window))
        normalized = []
        for draw_id in draw_ids:
            if isinstance(draw_id, bool) or not isinstance(draw_id, int):
                raise PromotionEligibilityError("DRAW_ID_INVALID", str(draw_id))
            normalized.append(draw_id)
        current = set(normalized)
        if len(current) != len(normalized):
            raise PromotionEligibilityError("WINDOW_DRAW_ID_DUPLICATE", str(draw_ids))
        if seen.intersection(current):
            raise PromotionEligibilityError("DRAW_WINDOW_OVERLAP", str(draw_ids))
        seen.update(current)

        metric_rows = window.get("metric_rows")
        if not isinstance(metric_rows, list) or not metric_rows:
            raise PromotionEligibilityError("WINDOW_METRICS_INVALID", str(window))
        available = {str(row.get("candidate_id", "")) for row in metric_rows}
        required = {candidate_id, *REQUIRED_BASELINES}
        if not required.issubset(available):
            raise PromotionEligibilityError("WINDOW_CANDIDATE_SET_MISMATCH", str(available))

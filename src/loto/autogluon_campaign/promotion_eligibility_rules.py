from __future__ import annotations

from typing import Any, Mapping

from loto.autogluon_campaign.holdout_prospective import _canon, _digest
from loto.autogluon_campaign.promotion_eligibility_contract import (
    PROMOTION_SCHEMA,
    REQUIRED_BASELINES,
    PromotionPolicy,
    aggregate_candidate_rows,
    validate_window_evidence,
)


def _rule(
    rule_id: str,
    passed: bool,
    observed: Any,
    requirement: Any,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "passed": bool(passed),
        "observed": observed,
        "requirement": requirement,
    }


def evaluate_promotion_rules(
    *,
    window_evidence: Mapping[str, Any],
    policy: PromotionPolicy,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    validate_window_evidence(window_evidence)
    holdout = dict(window_evidence["holdout"])
    prospective = [dict(item) for item in window_evidence["prospective"]]
    candidate_id = str(holdout["selected_candidate_id"])

    all_rows = [row for window in prospective for row in window["metric_rows"]]
    summaries = aggregate_candidate_rows(all_rows)
    summary_by_id = {str(row["candidate_id"]): row for row in summaries}
    selected = summary_by_id[candidate_id]

    window_summaries = []
    for window in prospective:
        current = aggregate_candidate_rows(window["metric_rows"])
        by_id = {str(row["candidate_id"]): row for row in current}
        window_summaries.append(
            {
                "source_run_id": window["source_run_id"],
                "draw_ids": list(window["draw_ids"]),
                "drift_state": window["drift_state"],
                "selected_metrics": by_id[candidate_id],
            }
        )

    holdout_summaries = aggregate_candidate_rows(holdout["metric_rows"])
    holdout_by_id = {str(row["candidate_id"]): row for row in holdout_summaries}
    holdout_selected = holdout_by_id[candidate_id]

    draw_ids = sorted({int(draw_id) for window in prospective for draw_id in window["draw_ids"]})
    worst_window_hit = min(
        float(window["selected_metrics"]["mean_hit_at_1"]) for window in window_summaries
    )
    hit_drop = float(holdout_selected["mean_hit_at_1"]) - float(selected["mean_hit_at_1"])
    mae_increase = float(selected["mean_mae"]) - float(holdout_selected["mean_mae"])

    baseline_results = []
    for baseline_id in REQUIRED_BASELINES:
        baseline = summary_by_id[baseline_id]
        hit_pass = float(selected["mean_hit_at_1"]) >= float(baseline["mean_hit_at_1"])
        mae_pass = float(selected["mean_mae"]) <= float(baseline["mean_mae"])
        baseline_results.append(
            {
                "baseline_id": baseline_id,
                "selected_mean_hit_at_1": selected["mean_hit_at_1"],
                "baseline_mean_hit_at_1": baseline["mean_hit_at_1"],
                "selected_mean_mae": selected["mean_mae"],
                "baseline_mean_mae": baseline["mean_mae"],
                "passed": hit_pass and mae_pass,
            }
        )

    aggregate = {
        "selected_candidate_id": candidate_id,
        "holdout_selected_metrics": holdout_selected,
        "prospective_selected_metrics": selected,
        "prospective_window_count": len(prospective),
        "prospective_draw_count": len(draw_ids),
        "prospective_draw_ids": draw_ids,
        "worst_window_hit_at_1": worst_window_hit,
        "holdout_to_prospective_hit_at_1_drop": hit_drop,
        "holdout_to_prospective_mae_increase": mae_increase,
        "window_summaries": window_summaries,
        "baseline_results": baseline_results,
    }

    rules = [
        _rule(
            "MINIMUM_PROSPECTIVE_WINDOWS",
            len(prospective) >= policy.minimum_prospective_windows,
            len(prospective),
            policy.minimum_prospective_windows,
        ),
        _rule(
            "MINIMUM_PROSPECTIVE_DRAWS",
            len(draw_ids) >= policy.minimum_prospective_draws,
            len(draw_ids),
            policy.minimum_prospective_draws,
        ),
        _rule(
            "ALL_WINDOWS_STABLE",
            (
                not policy.require_all_windows_stable
                or all(window["drift_state"] == "STABLE" for window in prospective)
            ),
            [window["drift_state"] for window in prospective],
            "all STABLE",
        ),
        _rule(
            "AGGREGATE_HIT_AT_1_TARGET",
            float(selected["mean_hit_at_1"]) >= policy.hit_at_1_target,
            selected["mean_hit_at_1"],
            policy.hit_at_1_target,
        ),
        _rule(
            "WORST_WINDOW_HIT_AT_1_TARGET",
            worst_window_hit >= policy.hit_at_1_target,
            worst_window_hit,
            policy.hit_at_1_target,
        ),
        _rule(
            "HOLDOUT_TO_PROSPECTIVE_HIT_DROP",
            hit_drop <= policy.maximum_hit_at_1_drop,
            hit_drop,
            policy.maximum_hit_at_1_drop,
        ),
        _rule(
            "HOLDOUT_TO_PROSPECTIVE_MAE_INCREASE",
            mae_increase <= policy.maximum_mae_increase,
            mae_increase,
            policy.maximum_mae_increase,
        ),
        _rule(
            "ALL_BASELINES_BEATEN",
            (
                not policy.require_all_baselines_beaten
                or all(row["passed"] for row in baseline_results)
            ),
            baseline_results,
            "selected hit >= and MAE <= every baseline",
        ),
    ]

    first_failure = next((row for row in rules if not row["passed"]), None)
    if first_failure is None:
        decision_value = "ELIGIBLE_FOR_HUMAN_APPROVAL"
        reason_code = "ALL_RULES_PASS"
    else:
        decision_value = "NOT_ELIGIBLE"
        reason_code = str(first_failure["rule_id"])

    core = {
        "schema_version": PROMOTION_SCHEMA,
        "status": "PASS",
        "decision": decision_value,
        "reason_code": reason_code,
        "selected_candidate_id": candidate_id,
        "human_approval_required": True,
        "human_approval_granted": False,
        "automatic_promotion": False,
        "automatic_retraining": False,
        "registry_write_allowed": False,
        "promotion_status": "NOT_PROMOTED",
    }
    decision = {**core, "decision_sha256": _digest(_canon(core))}
    return aggregate, rules, decision

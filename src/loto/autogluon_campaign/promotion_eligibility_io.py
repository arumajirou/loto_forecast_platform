from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loto.autogluon_campaign.holdout_prospective import (
    HoldoutProspectiveError,
    _tree_hash,
)
from loto.autogluon_campaign.holdout_prospective_score import (
    verify_scoring_output,
)
from loto.autogluon_campaign.promotion_eligibility_contract import (
    REQUIRED_BASELINES,
    PromotionEligibilityError,
    normalize_metric_row,
)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromotionEligibilityError("JSON_INVALID", str(path)) from exc


def read_scoring_window(root: Path) -> dict[str, Any]:
    root = root.resolve()
    try:
        verified = verify_scoring_output(root)
    except HoldoutProspectiveError as exc:
        raise PromotionEligibilityError(exc.code, str(exc)) from exc
    before = str(verified["tree_sha256"])
    report = dict(verified["report"])
    actuals = load_json(root / "ACTUALS_SNAPSHOT.json")
    metric_payload = load_json(root / "PER_PREDICTION_METRICS.json")
    baseline_payload = load_json(root / "BASELINE_COMPARISON.json")

    rows = metric_payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise PromotionEligibilityError("PER_PREDICTION_METRICS_INVALID", str(root))
    normalized_rows = [normalize_metric_row(row) for row in rows]

    actual_rows = actuals.get("rows")
    if not isinstance(actual_rows, list) or not actual_rows:
        raise PromotionEligibilityError("ACTUALS_SNAPSHOT_INVALID", str(root))
    draw_ids = []
    for row in actual_rows:
        draw_id = row.get("draw_id") if isinstance(row, Mapping) else None
        if isinstance(draw_id, bool) or not isinstance(draw_id, int):
            raise PromotionEligibilityError("ACTUAL_DRAW_ID_INVALID", str(draw_id))
        draw_ids.append(draw_id)
    if len(set(draw_ids)) != len(draw_ids):
        raise PromotionEligibilityError("ACTUAL_DRAW_ID_DUPLICATE", str(draw_ids))

    comparison_rows = baseline_payload.get("rows")
    if not isinstance(comparison_rows, list):
        raise PromotionEligibilityError("BASELINE_COMPARISON_INVALID", str(root))
    baseline_ids = [str(row.get("baseline_id", "")) for row in comparison_rows]
    if set(baseline_ids) != set(REQUIRED_BASELINES):
        raise PromotionEligibilityError("BASELINE_SET_MISMATCH", str(baseline_ids))
    if len(baseline_ids) != len(set(baseline_ids)):
        raise PromotionEligibilityError("BASELINE_DUPLICATE", str(baseline_ids))

    candidate_id = str(report.get("selected_candidate_id", "")).strip()
    if not candidate_id:
        raise PromotionEligibilityError("SELECTED_CANDIDATE_MISSING", str(root))
    if report.get("status") != "PASS":
        raise PromotionEligibilityError("SCORING_STATUS_NOT_PASS", str(root))
    if report.get("automatic_promotion") is not False:
        raise PromotionEligibilityError("UPSTREAM_AUTO_PROMOTION_INVALID", str(root))
    if report.get("automatic_retraining") is not False:
        raise PromotionEligibilityError("UPSTREAM_AUTO_RETRAIN_INVALID", str(root))

    selected_rows = [row for row in normalized_rows if row["candidate_id"] == candidate_id]
    if not selected_rows:
        raise PromotionEligibilityError("SELECTED_METRICS_MISSING", str(root))
    selected_seeds = {int(row["seed"]) for row in selected_rows}
    if len(selected_seeds) < 3:
        raise PromotionEligibilityError("SELECTED_SEED_COUNT_INSUFFICIENT", str(root))
    selected_coverage = {(int(row["seed"]), int(row["draw_id"])) for row in selected_rows}
    expected_coverage = {(seed, draw_id) for seed in selected_seeds for draw_id in draw_ids}
    if selected_coverage != expected_coverage:
        raise PromotionEligibilityError("SELECTED_SEED_DRAW_COVERAGE_MISMATCH", str(root))
    available_ids = {row["candidate_id"] for row in normalized_rows}
    if not set(REQUIRED_BASELINES).issubset(available_ids):
        raise PromotionEligibilityError("BASELINE_METRICS_MISSING", str(root))

    if before != _tree_hash(root):
        raise PromotionEligibilityError("UPSTREAM_SOURCE_MUTATED", str(root))
    result = {
        "stage": str(report.get("stage", "")),
        "source_run_id": str(report.get("source_run_id", "")),
        "source_tree_sha256": before,
        "source_report_sha256": str(report.get("report_sha256", "")),
        "selected_candidate_id": candidate_id,
        "draw_ids": sorted(draw_ids),
        "drift_state": str(report.get("drift_state", "NOT_APPLICABLE")),
        "operational_state": str(report.get("operational_state", "")),
        "metric_rows": normalized_rows,
    }
    game_id = str(report.get("game_id", "")).strip()
    if game_id:
        result["game_id"] = game_id
    return result

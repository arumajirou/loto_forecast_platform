from __future__ import annotations

import json
import statistics as stats
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from loto.autogluon_campaign.holdout_prospective import (
    REQUIRED_BASELINES,
    SCORE_SCHEMA,
    DriftPolicy,
    GeometryContract,
    HoldoutProspectiveError,
    ScoreResult,
    _canon,
    _digest,
    _empty,
    _prediction_rows,
    _tree_hash,
    _vector,
    _verify_hashes,
    _write,
    _write_evidence,
    compute_metrics,
)
from loto.autogluon_campaign.holdout_prospective_lock import verify_prediction_lock


def _aggregate(rows: Sequence[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    grouped: dict[tuple[str, int], list[dict]] = {}
    for row in rows:
        grouped.setdefault((row["candidate_id"], row["seed"]), []).append(row)
    per_seed = []
    for (candidate, seed), values in sorted(grouped.items()):
        per_seed.append(
            {
                "candidate_id": candidate,
                "seed": seed,
                "hit_at_1": stats.fmean(row["hit_at_1"] for row in values),
                "all_position_hit_at_1": stats.fmean(
                    row["all_position_hit_at_1"] for row in values
                ),
                "mae": stats.fmean(row["mae"] for row in values),
                "mse": stats.fmean(row["mse"] for row in values),
                "rmse": stats.fmean(row["rmse"] for row in values),
            }
        )
    candidates: dict[str, list[dict]] = {}
    for row in per_seed:
        candidates.setdefault(row["candidate_id"], []).append(row)
    summaries = []
    for candidate, values in sorted(candidates.items()):
        hits = [row["hit_at_1"] for row in values]
        maes = [row["mae"] for row in values]
        summaries.append(
            {
                "candidate_id": candidate,
                "seed_count": len(values),
                "mean_hit_at_1": stats.fmean(hits),
                "variance_hit_at_1": stats.pvariance(hits) if len(hits) > 1 else 0.0,
                "worst_hit_at_1": min(hits),
                "mean_all_position_hit_at_1": stats.fmean(
                    row["all_position_hit_at_1"] for row in values
                ),
                "mean_mae": stats.fmean(maes),
                "variance_mae": stats.pvariance(maes) if len(maes) > 1 else 0.0,
                "worst_mae": max(maes),
                "mean_mse": stats.fmean(row["mse"] for row in values),
                "mean_rmse": stats.fmean(row["rmse"] for row in values),
            }
        )
    return per_seed, summaries


def _drift(current: Mapping[str, Any], reference: Mapping[str, Any], policy: DriftPolicy):
    hit_drop = reference["mean_hit_at_1"] - current["mean_hit_at_1"]
    mae_increase = current["mean_mae"] - reference["mean_mae"]
    if hit_drop >= policy.critical_hit_drop or mae_increase >= policy.critical_mae_increase:
        state, action = "CRITICAL", "BLOCK_PROMOTION_RETRAIN_REVIEW_REQUIRED"
    elif hit_drop >= policy.warning_hit_drop or current["mean_hit_at_1"] < policy.hit_target:
        state, action = "WARNING", "CONTINUE_SHADOW_REVIEW_REQUIRED"
    else:
        state, action = "STABLE", "CONTINUE_SHADOW"
    return {
        "state": state,
        "action": action,
        "hit_at_1_drop": hit_drop,
        "mae_increase": mae_increase,
        "automatic_retraining": False,
    }


def verify_scoring_output(root: Path) -> dict[str, Any]:
    root = root.resolve()
    required = {
        "ACTUALS_SNAPSHOT.json",
        "SOURCE_LINEAGE.json",
        "PER_PREDICTION_METRICS.json",
        "PER_SEED_METRICS.json",
        "CANDIDATE_AGGREGATES.json",
        "LEADERBOARD.json",
        "BASELINE_COMPARISON.json",
        "SCORING_REPORT.json",
        "ARTIFACT_MANIFEST.json",
        "SHA256SUMS",
    }
    observed = _verify_hashes(root, "SCORE")
    if not required.issubset(observed) or observed - required - {"DRIFT_REPORT.json"}:
        raise HoldoutProspectiveError("SCORE_FILE_SET_MISMATCH", str(observed))
    report = json.loads((root / "SCORING_REPORT.json").read_text())
    claimed = report.pop("report_sha256")
    if claimed != _digest(_canon(report)):
        raise HoldoutProspectiveError("SCORE_REPORT_HASH_MISMATCH", claimed)
    report["report_sha256"] = claimed
    return {"report": report, "tree_sha256": _tree_hash(root)}


def score_prediction_lock(
    *,
    lock_dir: Path,
    output_dir: Path,
    actual_rows: Sequence[Mapping[str, Any]],
    actual_source_label: str,
    actual_observed_at: datetime | None = None,
    drift_policy: DriftPolicy = DriftPolicy(),
) -> ScoreResult:
    if not actual_source_label.strip():
        raise HoldoutProspectiveError(
            "ACTUAL_SOURCE_LABEL_REQUIRED",
            "actual_source_label must not be empty",
        )
    source = lock_dir.resolve()
    lock = verify_prediction_lock(source)
    before = _tree_hash(source)
    geometry = GeometryContract.model_validate(json.loads((source / "GEOMETRY.json").read_text()))
    actuals = {int(row["draw_id"]): _vector(row, geometry) for row in actual_rows}
    if set(actuals) != set(lock["future_draw_ids"]) or len(actuals) != len(actual_rows):
        raise HoldoutProspectiveError("ACTUAL_DRAW_SET_MISMATCH", str(actuals))
    rows = []
    for name in ("MODEL_PREDICTIONS.json", "BASELINE_PREDICTIONS.json"):
        rows.extend(_prediction_rows(json.loads((source / name).read_text())["rows"]))
    metric_rows = []
    for row in rows:
        metric_rows.append(
            {
                "candidate_id": row.candidate_id,
                "seed": row.seed,
                "draw_id": row.draw_id,
                **asdict(compute_metrics(row.values, actuals[row.draw_id])),
            }
        )
    per_seed, candidates = _aggregate(metric_rows)
    selected = next(
        row for row in candidates if row["candidate_id"] == lock["selected_candidate_id"]
    )
    leaderboard = sorted(
        candidates,
        key=lambda row: (-row["mean_hit_at_1"], row["mean_mae"], row["candidate_id"]),
    )
    comparison = [
        {
            "baseline_id": row["candidate_id"],
            "hit_at_1_delta": selected["mean_hit_at_1"] - row["mean_hit_at_1"],
            "mae_delta": selected["mean_mae"] - row["mean_mae"],
        }
        for row in candidates
        if row["candidate_id"] in REQUIRED_BASELINES
    ]
    root = _empty(output_dir)
    observed_at = actual_observed_at or datetime.now(timezone.utc)
    payloads = {
        "ACTUALS_SNAPSHOT.json": {
            "source_label": actual_source_label,
            "observed_at": observed_at.isoformat(),
            "publication_time_verified": False,
            "rows": [dict(row) for row in actual_rows],
        },
        "SOURCE_LINEAGE.json": {
            "source_tree_sha256": before,
            "source_lock_sha256": lock["lock_sha256"],
        },
        "PER_PREDICTION_METRICS.json": {"rows": metric_rows},
        "PER_SEED_METRICS.json": {"rows": per_seed},
        "CANDIDATE_AGGREGATES.json": {"rows": candidates},
        "LEADERBOARD.json": {"rows": leaderboard},
        "BASELINE_COMPARISON.json": {"rows": comparison},
    }
    operational = "HOLDOUT_SCORED_NOT_PROMOTED_PROSPECTIVE_REQUIRED"
    drift_state = "NOT_APPLICABLE"
    if lock["stage"] == "prospective":
        selection = json.loads((source / "SELECTION_EVIDENCE.json").read_text())
        drift = _drift(selected, selection["holdout_reference_metrics"], drift_policy)
        payloads["DRIFT_REPORT.json"] = drift
        operational, drift_state = drift["action"], drift["state"]
    for name, payload in payloads.items():
        _write(root / name, payload)
    core = {
        "schema_version": SCORE_SCHEMA,
        "status": "PASS",
        "stage": lock["stage"],
        "source_run_id": lock["run_id"],
        "selected_candidate_id": lock["selected_candidate_id"],
        "selected_candidate_metrics": selected,
        "required_baselines": list(REQUIRED_BASELINES),
        "baseline_count": len(comparison),
        "best_seed_selection": False,
        "automatic_promotion": False,
        "automatic_retraining": False,
        "promotion_status": "NOT_PROMOTED",
        "operational_state": operational,
        "drift_state": drift_state,
    }
    report = {**core, "report_sha256": _digest(_canon(core))}
    _write(root / "SCORING_REPORT.json", report)
    _write_evidence(root, [*payloads, "SCORING_REPORT.json"])
    if before != _tree_hash(source):
        raise HoldoutProspectiveError("SOURCE_LOCK_MUTATED", str(source))
    verify_scoring_output(root)
    return ScoreResult(
        str(root),
        str(root / "SCORING_REPORT.json"),
        "PASS",
        lock["stage"],
        lock["selected_candidate_id"],
        operational,
    )

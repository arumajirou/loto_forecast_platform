from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from loto.autogluon_campaign.holdout_prospective import (
    _canon,
    _digest,
    _write,
    _write_evidence,
)
from loto.autogluon_campaign.promotion_eligibility import (
    create_promotion_eligibility,
)

BASELINES = (
    "baseline_random",
    "baseline_fixed",
    "baseline_mean",
    "baseline_median",
    "baseline_last",
    "baseline_frequency",
    "baseline_ar1",
)
CANDIDATE = "TFT-known-past-static"


def metric_rows(
    *,
    draw_ids: list[int],
    selected_hit: float = 0.95,
    selected_mae: float = 0.30,
    baseline_hit: float = 0.50,
    baseline_mae: float = 1.50,
) -> list[dict]:
    rows = []
    for seed in (1, 2, 3):
        for draw_id in draw_ids:
            rows.append(
                {
                    "candidate_id": CANDIDATE,
                    "seed": seed,
                    "draw_id": draw_id,
                    "hit_at_1": selected_hit,
                    "all_position_hit_at_1": selected_hit,
                    "mae": selected_mae,
                    "mse": selected_mae**2,
                    "rmse": selected_mae,
                }
            )
            rows.append(
                {
                    "candidate_id": "baseline_random",
                    "seed": seed,
                    "draw_id": draw_id,
                    "hit_at_1": baseline_hit,
                    "all_position_hit_at_1": baseline_hit,
                    "mae": baseline_mae,
                    "mse": baseline_mae**2,
                    "rmse": baseline_mae,
                }
            )
    for baseline in BASELINES[1:]:
        for draw_id in draw_ids:
            rows.append(
                {
                    "candidate_id": baseline,
                    "seed": 0,
                    "draw_id": draw_id,
                    "hit_at_1": baseline_hit,
                    "all_position_hit_at_1": baseline_hit,
                    "mae": baseline_mae,
                    "mse": baseline_mae**2,
                    "rmse": baseline_mae,
                }
            )
    return rows


def score_bundle(
    root: Path,
    *,
    stage: str,
    run_id: str,
    draw_ids: list[int],
    candidate_id: str = CANDIDATE,
    drift_state: str = "STABLE",
    selected_hit: float = 0.95,
    selected_mae: float = 0.30,
    baseline_hit: float = 0.50,
    baseline_mae: float = 1.50,
    game_id: str | None = None,
) -> Path:
    root.mkdir(parents=True)
    rows = metric_rows(
        draw_ids=draw_ids,
        selected_hit=selected_hit,
        selected_mae=selected_mae,
        baseline_hit=baseline_hit,
        baseline_mae=baseline_mae,
    )
    if candidate_id != CANDIDATE:
        for row in rows:
            if row["candidate_id"] == CANDIDATE:
                row["candidate_id"] = candidate_id
    payloads = {
        "ACTUALS_SNAPSHOT.json": {
            "source_label": "fixture",
            "rows": [{"draw_id": draw_id, "value": 1} for draw_id in draw_ids],
        },
        "SOURCE_LINEAGE.json": {"source_lock_sha256": "a" * 64},
        "PER_PREDICTION_METRICS.json": {"rows": rows},
        "PER_SEED_METRICS.json": {"rows": []},
        "CANDIDATE_AGGREGATES.json": {"rows": []},
        "LEADERBOARD.json": {"rows": []},
        "BASELINE_COMPARISON.json": {"rows": [{"baseline_id": item} for item in BASELINES]},
    }
    if stage == "prospective":
        payloads["DRIFT_REPORT.json"] = {"state": drift_state}
    for name, payload in payloads.items():
        _write(root / name, payload)
    core = {
        "schema_version": "autogluon-holdout-prospective-score-v1",
        "status": "PASS",
        "stage": stage,
        "source_run_id": run_id,
        "selected_candidate_id": candidate_id,
        "selected_candidate_metrics": {},
        "required_baselines": list(BASELINES),
        "baseline_count": 7,
        "best_seed_selection": False,
        "automatic_promotion": False,
        "automatic_retraining": False,
        "promotion_status": "NOT_PROMOTED",
        "operational_state": "CONTINUE_SHADOW",
        "drift_state": drift_state if stage == "prospective" else "NOT_APPLICABLE",
    }
    if game_id is not None:
        core["game_id"] = game_id
    report = {**core, "report_sha256": _digest(_canon(core))}
    _write(root / "SCORING_REPORT.json", report)
    _write_evidence(root, [*payloads, "SCORING_REPORT.json"])
    return root


def valid_sources(tmp_path: Path, *, game_id: str | None = None):
    holdout = score_bundle(
        tmp_path / "holdout",
        stage="holdout",
        run_id="holdout-1",
        draw_ids=[10, 11],
        selected_hit=0.96,
        selected_mae=0.25,
        game_id=game_id,
    )
    prospective = [
        score_bundle(
            tmp_path / f"prospective-{index}",
            stage="prospective",
            run_id=f"prospective-{index}",
            draw_ids=[11 + index],
            selected_hit=0.95,
            selected_mae=0.30,
            game_id=game_id,
        )
        for index in (1, 2, 3)
    ]
    return holdout, prospective


def run_gate(tmp_path: Path, *, holdout=None, prospective=None, policy=None):
    if holdout is None or prospective is None:
        holdout, prospective = valid_sources(tmp_path)
    kwargs = {
        "holdout_score_dir": holdout,
        "prospective_score_dirs": prospective,
        "output_dir": tmp_path / "promotion",
        "run_id": "p17-fixture",
        "now": datetime(2026, 8, 5, 10, 0, tzinfo=UTC),
    }
    if policy is not None:
        kwargs["policy"] = policy
    return create_promotion_eligibility(**kwargs)

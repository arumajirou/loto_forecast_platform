from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from loto.autogluon_campaign.holdout_prospective import (
    GeometryContract,
    HoldoutProspectiveError,
    SelectionEvidence,
    build_baseline_predictions,
    compute_metrics,
    create_prediction_lock,
    score_prediction_lock,
    verify_prediction_lock,
    verify_scoring_output,
)


def geometry() -> GeometryContract:
    return GeometryContract(
        game_id="numbers3",
        position_columns=("n1", "n2", "n3"),
        candidate_min=0,
        candidate_max=9,
        selection_count=3,
        horizon=2,
        allow_duplicates=False,
        sort_policy="ascending",
    )


def history() -> list[dict]:
    return [
        {"draw_id": index, "n1": index % 3, "n2": 3 + index % 3, "n3": 6 + index % 3}
        for index in range(1, 13)
    ]


def selection() -> SelectionEvidence:
    return SelectionEvidence(
        selection_id="oof-selection-v1",
        selected_candidate_id="TFT-known-past-static",
        model_seeds=(1, 2, 3),
        selection_source_sha256="a" * 64,
        automatic_selection=False,
    )


def model_predictions(values=None) -> list[dict]:
    rows = []
    for seed in (1, 2, 3):
        for draw_id in (13, 14):
            current = values or (2 + seed / 10, 5 + seed / 10, 8 + seed / 10)
            rows.append(
                {
                    "candidate_id": "TFT-known-past-static",
                    "seed": seed,
                    "draw_id": draw_id,
                    "values": current,
                }
            )
    return rows


def actuals(values=(2, 5, 8)) -> list[dict]:
    return [
        {"draw_id": 13, "n1": values[0], "n2": values[1], "n3": values[2]},
        {"draw_id": 14, "n1": values[0], "n2": values[1], "n3": values[2]},
    ]


def make_holdout(tmp_path: Path) -> Path:
    root = tmp_path / "holdout-lock"
    create_prediction_lock(
        output_dir=root,
        stage="holdout",
        run_id="p16-holdout",
        geometry=geometry(),
        history_rows=history(),
        future_draw_ids=(13, 14),
        selection=selection(),
        model_predictions=model_predictions(),
        now=datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc),
    )
    return root


def test_metrics_include_hit_error_and_all_position() -> None:
    result = compute_metrics((2, 5, 8), (1, 5, 9))
    assert result.hit_at_1 == 1.0
    assert result.all_position_hit_at_1 == 1.0
    assert result.exact_hit_rate == pytest.approx(1 / 3)
    assert result.mae == pytest.approx(2 / 3)
    assert result.mse == pytest.approx(2 / 3)


def test_required_baselines_and_random_reproducibility() -> None:
    first = build_baseline_predictions(history(), (13, 14), geometry())
    second = build_baseline_predictions(history(), (13, 14), geometry())
    assert first == second
    assert {row.candidate_id for row in first} == {
        "baseline_random",
        "baseline_fixed",
        "baseline_mean",
        "baseline_median",
        "baseline_last",
        "baseline_frequency",
        "baseline_ar1",
    }
    assert {row.seed for row in first if row.candidate_id == "baseline_random"} == {1, 2, 3}


def test_holdout_lock_is_created_and_verified(tmp_path: Path) -> None:
    root = make_holdout(tmp_path)
    lock = verify_prediction_lock(root)
    assert lock["actual_known"] is False
    assert lock["evaluation_status"] == "NOT_SCORED"
    assert lock["promotion_status"] == "SHADOW_NOT_PROMOTED"
    assert lock["model_seeds"] == [1, 2, 3]


def test_prediction_lock_rejects_actual_bearing_history(tmp_path: Path) -> None:
    rows = history()
    rows[0]["actual_n1"] = 1
    with pytest.raises(HoldoutProspectiveError) as exc_info:
        create_prediction_lock(
            output_dir=tmp_path / "blocked",
            stage="holdout",
            run_id="blocked",
            geometry=geometry(),
            history_rows=rows,
            future_draw_ids=(13, 14),
            selection=selection(),
            model_predictions=model_predictions(),
        )
    assert exc_info.value.code == "ACTUAL_FIELD_FORBIDDEN"


def test_model_seed_coverage_is_fail_closed(tmp_path: Path) -> None:
    rows = model_predictions()[:-1]
    with pytest.raises(HoldoutProspectiveError) as exc_info:
        create_prediction_lock(
            output_dir=tmp_path / "blocked",
            stage="holdout",
            run_id="blocked",
            geometry=geometry(),
            history_rows=history(),
            future_draw_ids=(13, 14),
            selection=selection(),
            model_predictions=rows,
        )
    assert exc_info.value.code == "MODEL_SEED_DRAW_COVERAGE_MISMATCH"


def test_lock_tampering_is_detected(tmp_path: Path) -> None:
    root = make_holdout(tmp_path)
    path = root / "MODEL_PREDICTIONS.json"
    path.write_text(path.read_text(encoding="utf-8").replace("2.1", "9.1"), encoding="utf-8")
    with pytest.raises(HoldoutProspectiveError) as exc_info:
        verify_prediction_lock(root)
    assert exc_info.value.code == "LOCK_FILE_HASH_MISMATCH"


def test_holdout_scoring_is_read_only_and_never_promotes(tmp_path: Path) -> None:
    source = make_holdout(tmp_path)
    before = {path.name: path.read_bytes() for path in source.iterdir() if path.is_file()}
    result = score_prediction_lock(
        lock_dir=source,
        output_dir=tmp_path / "holdout-score",
        actual_rows=actuals(),
        actual_source_label="operator-verified fixture",
    )
    assert result.status == "PASS"
    report = verify_scoring_output(Path(result.output_dir))["report"]
    assert report["automatic_promotion"] is False
    assert report["promotion_status"] == "NOT_PROMOTED"
    assert report["best_seed_selection"] is False
    after = {path.name: path.read_bytes() for path in source.iterdir() if path.is_file()}
    assert before == after


def test_holdout_actual_draw_mismatch_is_rejected(tmp_path: Path) -> None:
    source = make_holdout(tmp_path)
    rows = actuals()
    rows[1]["draw_id"] = 15
    with pytest.raises(HoldoutProspectiveError) as exc_info:
        score_prediction_lock(
            lock_dir=source,
            output_dir=tmp_path / "score",
            actual_rows=rows,
            actual_source_label="fixture",
        )
    assert exc_info.value.code == "ACTUAL_DRAW_SET_MISMATCH"


def test_prospective_requires_verified_holdout_score(tmp_path: Path) -> None:
    with pytest.raises(HoldoutProspectiveError) as exc_info:
        create_prediction_lock(
            output_dir=tmp_path / "prospective",
            stage="prospective",
            run_id="p16-prospective",
            geometry=geometry(),
            history_rows=history(),
            future_draw_ids=(13, 14),
            selection=selection(),
            model_predictions=model_predictions(),
        )
    assert exc_info.value.code == "HOLDOUT_SCORE_REQUIRED"


def test_prospective_keeps_shadow_candidate_and_scores_drift(tmp_path: Path) -> None:
    holdout = make_holdout(tmp_path)
    holdout_score = tmp_path / "holdout-score"
    score_prediction_lock(
        lock_dir=holdout,
        output_dir=holdout_score,
        actual_rows=actuals(),
        actual_source_label="holdout fixture",
    )
    prospective_history = history() + [
        {"draw_id": 13, "n1": 2, "n2": 5, "n3": 8},
        {"draw_id": 14, "n1": 2, "n2": 5, "n3": 8},
    ]
    prospective = tmp_path / "prospective-lock"
    predictions = []
    for seed in (1, 2, 3):
        for draw_id in (15, 16):
            predictions.append(
                {
                    "candidate_id": "TFT-known-past-static",
                    "seed": seed,
                    "draw_id": draw_id,
                    "values": (8.5, 8.5, 8.5),
                }
            )
    create_prediction_lock(
        output_dir=prospective,
        stage="prospective",
        run_id="p16-prospective",
        geometry=geometry(),
        history_rows=prospective_history,
        future_draw_ids=(15, 16),
        selection=selection(),
        model_predictions=predictions,
        predecessor_score_dir=holdout_score,
    )
    result = score_prediction_lock(
        lock_dir=prospective,
        output_dir=tmp_path / "prospective-score",
        actual_rows=[
            {"draw_id": 15, "n1": 0, "n2": 3, "n3": 6},
            {"draw_id": 16, "n1": 0, "n2": 3, "n3": 6},
        ],
        actual_source_label="prospective fixture",
    )
    report = verify_scoring_output(Path(result.output_dir))["report"]
    assert report["selected_candidate_id"] == "TFT-known-past-static"
    assert report["drift_state"] in {"WARNING", "CRITICAL"}
    assert report["automatic_retraining"] is False


def test_prospective_rejects_candidate_change(tmp_path: Path) -> None:
    holdout = make_holdout(tmp_path)
    holdout_score = tmp_path / "holdout-score"
    score_prediction_lock(
        lock_dir=holdout,
        output_dir=holdout_score,
        actual_rows=actuals(),
        actual_source_label="holdout fixture",
    )
    changed = selection().model_copy(update={"selected_candidate_id": "DeepAR-known-static"})
    changed_rows = [
        {**row, "candidate_id": "DeepAR-known-static"} for row in model_predictions()
    ]
    with pytest.raises(HoldoutProspectiveError) as exc_info:
        create_prediction_lock(
            output_dir=tmp_path / "prospective",
            stage="prospective",
            run_id="p16-prospective",
            geometry=geometry(),
            history_rows=history(),
            future_draw_ids=(13, 14),
            selection=changed,
            model_predictions=changed_rows,
            predecessor_score_dir=holdout_score,
        )
    assert exc_info.value.code == "SHADOW_CANDIDATE_CHANGED"


def test_scoring_output_tamper_is_detected(tmp_path: Path) -> None:
    source = make_holdout(tmp_path)
    score = tmp_path / "score"
    score_prediction_lock(
        lock_dir=source,
        output_dir=score,
        actual_rows=actuals(),
        actual_source_label="fixture",
    )
    path = score / "SCORING_REPORT.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["promotion_status"] = "PROMOTED"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(HoldoutProspectiveError) as exc_info:
        verify_scoring_output(score)
    assert exc_info.value.code == "SCORE_FILE_HASH_MISMATCH"

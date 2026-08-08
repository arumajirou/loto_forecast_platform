from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from loto.sktime_campaign.benchmark import FORMAL_BASELINES, canonical_sha256
from loto.sktime_campaign.holdout_scoring import (
    HoldoutActuals,
    HoldoutScoringRequest,
    build_holdout_leaderboard,
    expected_formal_lock_keys,
    score_holdout,
    validate_lock_for_scoring,
)


def _seal(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _lock():
    rows = []
    for kind, candidate, seed in expected_formal_lock_keys():
        base = 0 if candidate == "last" else (seed % 2)
        prediction = [[float((row + col + base) % 10) for col in range(2)] for row in range(5)]
        rows.append(
            {
                "candidate_kind": kind,
                "candidate_id": candidate,
                "seed": seed,
                "status": "PASS",
                "fit_scope": "TRAIN_PLUS_VALIDATION_ONLY",
                "forecast_scope": "HOLDOUT_PREDICTION_ONLY",
                "actuals_known": False,
                "evaluation_status": "NOT_SCORED",
                "raw_predictions": prediction,
                "predictions": prediction,
                "prediction_sha256": canonical_sha256(prediction),
            }
        )
    payload = {
        "schema_version": "1.0",
        "lock_scope": "ALL_CANDIDATES_ALL_SEEDS_BEFORE_HOLDOUT_ACTUALS",
        "run_id": "p3-test",
        "sealed_at_utc": "2026-08-05T07:00:00Z",
        "git_commit": "abcdef1",
        "code_sha256": "1" * 64,
        "config_sha256": "2" * 64,
        "validation_artifact_sha256": "3" * 64,
        "visible_rows": 25,
        "visible_values_sha256": "4" * 64,
        "holdout_draw_no": [26, 27, 28, 29, 30],
        "holdout_draw_no_sha256": canonical_sha256([26, 27, 28, 29, 30]),
        "selected_oof_candidate_id": "last",
        "all_candidate_predictions_locked": True,
        "actuals_known": False,
        "evaluation_status": "NOT_SCORED",
        "prediction_rows": rows,
    }
    return {**payload, "seal_sha256": _seal(payload)}


def _actuals(revealed="2026-08-05T08:00:00Z"):
    return HoldoutActuals(
        game_id="numbers3-contract",
        revealed_at_utc=revealed,
        source_id="official-source",
        source_sha256="5" * 64,
        draw_no=[26, 27, 28, 29, 30],
        position_names=["N1", "N2"],
        values=[[float((row + col) % 10) for col in range(2)] for row in range(5)],
        legal_min=[0, 0],
        legal_max=[9, 9],
    )


def _request(lock=None, revealed="2026-08-05T08:00:00Z"):
    active = _lock() if lock is None else lock
    return HoldoutScoringRequest(
        output_dir="/tmp/p4",
        run_id="p4-test",
        git_commit="abcdef1",
        code_sha256="6" * 64,
        config_sha256="7" * 64,
        prediction_lock_file_sha256="8" * 64,
        expected_lock_seal_sha256=active["seal_sha256"],
        p3_sha256sums_sha256="9" * 64,
        scored_at_utc="2026-08-05T08:05:00Z",
        actuals=_actuals(revealed),
    )


def test_formal_score_uses_every_locked_candidate_seed():
    lock = _lock()
    result = score_holdout(_request(lock), lock)
    assert result["status"] == "PASS"
    assert len(result["holdout_results"]) == len(expected_formal_lock_keys())
    assert all(row["model_execution"] is False for row in result["holdout_results"])
    assert result["retraining"] is False
    assert result["reprediction"] is False


def test_metrics_and_position_metrics_are_retained():
    result = score_holdout(_request(), _lock())
    row = result["holdout_results"][0]
    assert {
        "hit_at_1",
        "mae",
        "mse",
        "rmse",
        "position_hit_at_1",
    } <= set(row["metrics"])
    aggregate = result["candidate_aggregates"][0]
    assert set(aggregate["metrics"]["hit_at_1"]) == {
        "mean",
        "variance",
        "worst",
    }
    assert set(aggregate["position_hit_at_1"]) == {"N1", "N2"}


def test_random_seed_aggregate_keeps_all_three_seeds():
    result = score_holdout(_request(), _lock())
    random_row = next(
        row for row in result["candidate_aggregates"] if row["candidate_id"] == "random_uniform"
    )
    assert random_row["seeds"] == [1, 2, 3]
    assert random_row["seed_count"] == 3


def test_leaderboard_is_deterministic():
    result = score_holdout(_request(), _lock())
    rebuilt = build_holdout_leaderboard(result["candidate_aggregates"])
    assert result["leaderboard"] == rebuilt


def test_selected_oof_candidate_is_compared_with_all_baselines():
    result = score_holdout(_request(), _lock())
    comparison = result["baseline_comparison"]
    assert comparison["status"] == "PASS"
    assert comparison["selected_oof_candidate_id"] == "last"
    assert len(comparison["baselines"]) == len(FORMAL_BASELINES)


def test_reveal_must_follow_seal():
    lock = _lock()
    with pytest.raises(ValueError, match="after prediction sealing"):
        score_holdout(
            _request(lock, revealed="2026-08-05T06:59:59Z"),
            lock,
        )


def test_draw_identity_mismatch_is_rejected():
    lock = _lock()
    payload = _request(lock).model_dump()
    payload["actuals"]["draw_no"][-1] = 31
    bad = HoldoutScoringRequest.model_validate(payload)
    with pytest.raises(ValueError, match="draw identities"):
        score_holdout(bad, lock)


def test_lock_tampering_is_rejected():
    lock = deepcopy(_lock())
    lock["prediction_rows"][0]["predictions"][0][0] += 1
    with pytest.raises(ValueError, match="SHA-256"):
        score_holdout(_request(_lock()), lock)


def test_formal_inventory_reduction_is_rejected():
    lock = _lock()
    lock["prediction_rows"] = lock["prediction_rows"][:-1]
    payload = {key: value for key, value in lock.items() if key != "seal_sha256"}
    lock["seal_sha256"] = _seal(payload)
    with pytest.raises(ValueError, match="inventory"):
        score_holdout(_request(lock), lock, formal=True)


def test_duplicate_candidate_seed_is_rejected():
    lock = _lock()
    lock["prediction_rows"].append(deepcopy(lock["prediction_rows"][0]))
    payload = {key: value for key, value in lock.items() if key != "seal_sha256"}
    lock["seal_sha256"] = _seal(payload)
    with pytest.raises(ValueError, match="duplicate"):
        validate_lock_for_scoring(lock, _request(lock), formal=False)


def test_locked_prediction_shape_mismatch_is_rejected():
    lock = _lock()
    lock["prediction_rows"][0]["predictions"] = [[1.0, 2.0]]
    lock["prediction_rows"][0]["prediction_sha256"] = canonical_sha256(
        lock["prediction_rows"][0]["predictions"]
    )
    payload = {key: value for key, value in lock.items() if key != "seal_sha256"}
    lock["seal_sha256"] = _seal(payload)
    with pytest.raises(ValueError, match="shape"):
        score_holdout(_request(lock), lock)


def test_promotion_remains_blocked_until_prospective():
    result = score_holdout(_request(), _lock())
    assert result["promotion_status"] == ("HOLDOUT_SCORED_NOT_PROMOTED_PROSPECTIVE_REQUIRED")

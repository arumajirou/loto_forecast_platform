from __future__ import annotations

import copy

import numpy as np
import pytest
from pydantic import ValidationError

from loto.sktime_campaign.prospective import (
    ObservedHistory,
    ProspectiveActuals,
    ProspectiveMonitoringRequest,
    ProspectiveRequest,
    monitor_prospective,
    run_prospective_lock,
    verify_prospective_lock,
)


def make_request(**overrides) -> ProspectiveRequest:
    history = ObservedHistory(
        game_id="numbers3-synthetic-contract",
        draw_no=list(range(1001, 1031)),
        position_names=["N1", "N2", "N3"],
        values=[
            [float(index % 10), float((index + 1) % 10), float((index + 2) % 10)]
            for index in range(30)
        ],
        legal_min=[0, 0, 0],
        legal_max=[9, 9, 9],
    )
    payload = {
        "output_dir": "/tmp/p5-test",
        "run_id": "p5-test",
        "git_commit": "abcdef1",
        "code_sha256": "1" * 64,
        "config_sha256": "2" * 64,
        "p4_artifact_sha256": "3" * 64,
        "p4_selected_oof_candidate_id": "naive_last",
        "p4_promotion_status": "NOT_PROMOTED",
        "history": history,
        "prospective_draw_no": [1031, 1032, 1033],
        "max_workers": 8,
    }
    payload.update(overrides)
    return ProspectiveRequest.model_validate(payload)


def model_predictor(model_id, history, horizon, request):
    del request
    offset = {
        "naive_last": 0.0,
        "polynomial_trend_d1": 1.0,
        "exponential_smoothing": 2.0,
        "theta": 3.0,
    }[model_id.value]
    raw = np.tile(history[-1] + offset, (horizon, 1))
    return {
        "candidate_kind": "sktime",
        "candidate_id": model_id.value,
        "status": "PASS",
        "raw_predictions": raw.tolist(),
    }


def make_lock(monkeypatch) -> dict:
    for name in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        monkeypatch.setenv(name, "1")
    return run_prospective_lock(
        make_request(),
        sealed_at_utc="2026-08-05T00:00:00Z",
        model_predictor=model_predictor,
    )["prediction_lock"]


def make_monitor_request(lock: dict, *, values=None, revealed_at=None):
    actuals = ProspectiveActuals(
        game_id="numbers3-synthetic-contract",
        revealed_at_utc=revealed_at or "2026-08-05T00:00:01Z",
        source_id="synthetic-contract",
        source_sha256="4" * 64,
        draw_no=[1031, 1032, 1033],
        position_names=["N1", "N2", "N3"],
        values=values
        or [
            [0.0, 1.0, 2.0],
            [1.0, 2.0, 3.0],
            [2.0, 3.0, 4.0],
        ],
    )
    return ProspectiveMonitoringRequest(
        run_id="p5-monitor-test",
        prediction_lock=lock,
        actuals=actuals,
        holdout_reference_metrics={
            "hit_at_1": {"mean": 0.95, "variance": 0.0, "worst": 0.95},
            "mae": {"mean": 0.20, "variance": 0.0, "worst": 0.20},
        },
    )


def test_prospective_ids_must_start_after_history() -> None:
    with pytest.raises(ValidationError):
        make_request(prospective_draw_no=[1030, 1031, 1032])


def test_formal_lock_has_all_candidate_seed_rows(monkeypatch) -> None:
    lock = make_lock(monkeypatch)
    assert len(lock["prediction_rows"]) == 13
    assert lock["max_workers"] == 8
    assert lock["shadow_candidate_id"] == "naive_last"
    assert lock["actuals_known"] is False
    assert lock["evaluation_status"] == "NOT_SCORED"
    assert lock["promotion_status"] == "SHADOW_NOT_PROMOTED"


def test_parallel_lock_is_deterministic(monkeypatch) -> None:
    first = make_lock(monkeypatch)
    second = make_lock(monkeypatch)
    assert first == second


def test_lock_contains_no_actuals_or_metrics(monkeypatch) -> None:
    lock = make_lock(monkeypatch)
    for row in lock["prediction_rows"]:
        assert "actuals" not in row
        assert "actual_values" not in row
        assert "metrics" not in row
        assert row["fit_scope"] == "OBSERVED_HISTORY_ONLY"
        assert row["forecast_scope"] == "PROSPECTIVE_DRAW_IDS_ONLY"


def test_lock_seal_detects_tamper(monkeypatch) -> None:
    lock = make_lock(monkeypatch)
    lock["prediction_rows"][0]["predictions"][0][0] += 1
    with pytest.raises(ValueError, match="SHA-256"):
        verify_prospective_lock(lock)


def test_lock_rejects_more_than_eight_workers() -> None:
    with pytest.raises(ValidationError):
        make_request(max_workers=9)


def test_monitor_requires_actual_reveal_after_seal(monkeypatch) -> None:
    lock = make_lock(monkeypatch)
    with pytest.raises(ValidationError):
        make_monitor_request(lock, revealed_at="2026-08-05T00:00:00Z")


def test_monitor_requires_exact_draw_identities(monkeypatch) -> None:
    lock = make_lock(monkeypatch)
    actuals = ProspectiveActuals(
        game_id="numbers3-synthetic-contract",
        revealed_at_utc="2026-08-05T00:00:01Z",
        source_id="synthetic-contract",
        source_sha256="4" * 64,
        draw_no=[1031, 1032, 1034],
        position_names=["N1", "N2", "N3"],
        values=[[0.0, 1.0, 2.0]] * 3,
    )
    with pytest.raises(ValidationError):
        ProspectiveMonitoringRequest(
            run_id="bad-draws",
            prediction_lock=lock,
            actuals=actuals,
            holdout_reference_metrics={
                "hit_at_1": {"mean": 0.9},
                "mae": {"mean": 0.5},
            },
        )


def test_monitor_scores_only_locked_predictions(monkeypatch) -> None:
    lock = make_lock(monkeypatch)
    result = monitor_prospective(make_monitor_request(lock))
    assert len(result["score_rows"]) == 13
    assert all(
        row["prediction_source"] == "P5_LOCK_ONLY_NO_REFIT_NO_REPREDICT"
        for row in result["score_rows"]
    )
    assert result["automatic_retraining"] is False
    assert result["automatic_promotion"] is False
    assert result["promotion_status"] == "NOT_PROMOTED"


def test_shadow_candidate_is_not_reselected_by_prospective_rank(monkeypatch) -> None:
    lock = make_lock(monkeypatch)
    result = monitor_prospective(make_monitor_request(lock))
    assert result["shadow_candidate_id"] == lock["shadow_candidate_id"]


def test_hit_target_failure_is_critical(monkeypatch) -> None:
    lock = make_lock(monkeypatch)
    far_actuals = [[9.0, 9.0, 9.0]] * 3
    result = monitor_prospective(make_monitor_request(lock, values=far_actuals))
    assert result["drift_status"] == "CRITICAL"
    assert result["recommendation"] == ("BLOCK_PROMOTION_RETRAIN_REVIEW_REQUIRED")
    assert any(alert["code"] == "HIT_AT_1_BELOW_TARGET" for alert in result["alerts"])


def test_lock_prediction_hashes_remain_valid(monkeypatch) -> None:
    lock = make_lock(monkeypatch)
    copied = copy.deepcopy(lock)
    verify_prospective_lock(copied)

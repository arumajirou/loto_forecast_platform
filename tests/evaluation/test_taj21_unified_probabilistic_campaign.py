from __future__ import annotations

import inspect
from types import SimpleNamespace

import numpy as np
import pandas as pd

from loto.evaluation import unified_campaign as campaign
from loto.evaluation.probabilistic_oof_adapter import (
    ProbabilisticOOFPrediction,
    ProbabilisticScientificRoute,
)
from loto.game.geometry import geometry_for


def _config(tmp_path, *, model_ids=None):
    return campaign.UnifiedCampaignConfig(
        output_dir=tmp_path / "run",
        git_commit="a" * 40,
        model_ids=model_ids,
        seeds=(42,),
        folds=1,
        test_size=1,
        min_train_size=10,
        holdout_size=0,
    )


def test_default_plan_is_exact_unified_250_by_6(tmp_path) -> None:
    config = _config(tmp_path)
    plan = campaign.build_campaign_plan(config)
    assert len(plan) == 1500
    assert len({(row["game"], row["candidate_id"]) for row in plan}) == 1500
    assert sum(row["library"] == "probabilistic" for row in plan) == 456
    assert sum(row["library"] != "probabilistic" for row in plan) == 1044
    assert len({row["candidate_id"] for row in plan}) == 250


def test_probabilistic_model_id_subset_routes_all_six_games(tmp_path) -> None:
    config = _config(tmp_path, model_ids=("pp-multinomial-dglm",))
    plan = campaign.build_campaign_plan(config)
    assert len(plan) == 6
    assert {row["candidate_id"] for row in plan} == {"pp-multinomial-dglm"}
    assert {row["game"] for row in plan} == set(config.games)
    assert {row["library"] for row in plan} == {"probabilistic"}


def test_probabilistic_seed_uses_history_only_and_scores_after_lock(tmp_path, monkeypatch) -> None:
    geometry = geometry_for("numbers3")
    frame = pd.DataFrame(
        {
            "draw_no": np.arange(1, 14),
            "d1": np.arange(13) % 10,
            "d2": (np.arange(13) + 2) % 10,
            "d3": (np.arange(13) + 4) % 10,
        }
    )
    fold = SimpleNamespace(fold_id=0, test_start=12, test_end=13)
    prepared = campaign.PreparedGame(
        geometry=geometry,
        development=frame,
        holdout_rows=0,
        folds=(fold,),
        protocol=SimpleNamespace(protocol_hash="b" * 64),
    )
    route = ProbabilisticScientificRoute(
        model_id="pp-multinomial-dglm",
        family="state_space",
        game="numbers3",
        target_mode="dynamic_multinomial",
        backend="builtin",
        inference_profile_id=None,
        resource_class="heavy_cpu",
        allowed=True,
        reason_code="ALLOWED",
        details=("target_mode=dynamic_multinomial",),
    )
    observed = {"history_rows": None, "sealed": False}

    def fake_predict(history, _route, **kwargs):
        observed["history_rows"] = len(history)
        assert kwargs["protocol_hash"] == "b" * 64
        return ProbabilisticOOFPrediction(
            values=(1, 2, 3),
            probabilities=np.full((3, 10), 0.1),
            metadata={"route": "probabilistic-test"},
        )

    def fake_lock(*args, **kwargs):
        observed["sealed"] = True
        return {"path": str(tmp_path / "lock.json"), "sha256": "c" * 64}

    def fake_metrics(actual, predicted, geometry, *, tau):
        assert observed["sealed"] is True
        return {
            "hit_at_1": 1.0,
            "position_hit_at_1": 1.0,
            "position_hit_at_1_by_position": {"1": 1.0, "2": 1.0, "3": 1.0},
            "all_positions_hit_at_1": 1.0,
            "mae": 0.0,
            "mse": 0.0,
            "rmse": 0.0,
        }

    monkeypatch.setattr(campaign, "predict_probabilistic_from_history", fake_predict)
    monkeypatch.setattr(campaign, "_write_prediction_lock", fake_lock)
    monkeypatch.setattr(campaign, "_canonical_metrics", fake_metrics)

    result = campaign._evaluate_seed(
        prepared,
        route.model_id,
        42,
        _config(tmp_path),
        probabilistic_route=route,
    )
    assert observed["history_rows"] == 12
    assert observed["sealed"] is True
    assert result["metrics"]["hit_at_1"] == 1.0

    source = inspect.getsource(campaign._evaluate_seed)
    assert source.index("lock = _write_prediction_lock") < source.index("actual = np.asarray")


def test_disallowed_probabilistic_route_is_explicit_without_execution(tmp_path, monkeypatch) -> None:
    geometry = geometry_for("numbers3")
    frame = pd.DataFrame(
        {"draw_no": [1], "d1": [1], "d2": [2], "d3": [3]}
    )
    prepared = campaign.PreparedGame(
        geometry=geometry,
        development=frame,
        holdout_rows=0,
        folds=(),
        protocol=SimpleNamespace(protocol_hash="d" * 64),
    )
    route = ProbabilisticScientificRoute(
        model_id="blocked-probabilistic",
        family="test",
        game="numbers3",
        target_mode=None,
        backend="missing",
        inference_profile_id=None,
        resource_class=None,
        allowed=False,
        reason_code="BACKEND_UNAVAILABLE",
        details=("backend unavailable",),
    )

    def should_not_run(*args, **kwargs):
        raise AssertionError("disallowed route must not execute")

    monkeypatch.setattr(campaign, "_evaluate_seed", should_not_run)
    result = campaign._evaluate_candidate(
        prepared,
        _config(tmp_path),
        candidate_id=route.model_id,
        source="probabilistic",
        library="probabilistic",
        task="probabilistic",
        probabilistic_route=route,
    )
    assert result["status"] == "UNAVAILABLE"
    assert "BACKEND_UNAVAILABLE" in result["reason"]

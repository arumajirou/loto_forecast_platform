from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from loto.evaluation.metric_registry import REQUIRED_BASELINE_IDS, REQUIRED_POINT_METRICS
from loto.evaluation.unified_campaign import (
    UnifiedCampaignConfig,
    build_campaign_plan,
    run_unified_campaign,
)
from loto.game.geometry import geometry_for, known_games
from loto.models.catalog_full import build_catalog


def _synthetic(game: str, *, rows: int = 32, seed: int = 7) -> pd.DataFrame:
    geometry = geometry_for(game)
    rng = np.random.default_rng(seed)
    payload = []
    for draw in range(rows):
        universe = np.arange(geometry.value_min, geometry.value_max + 1)
        if geometry.family == "select":
            values = np.sort(rng.choice(universe, size=geometry.positions, replace=False))
        else:
            values = rng.choice(universe, size=geometry.positions, replace=True)
        payload.append(
            {
                "draw_no": draw + 1,
                **dict(zip(geometry.column_names(), values.tolist(), strict=True)),
            }
        )
    return pd.DataFrame(payload)


def _config(tmp_path: Path, **updates) -> UnifiedCampaignConfig:
    base = {
        "output_dir": tmp_path / "campaign",
        "git_commit": "1" * 40,
        "seeds": (1, 2),
        "folds": 1,
        "test_size": 2,
        "min_train_size": 12,
        "holdout_size": 4,
        "max_trials": 1,
        "parallel_trials": 1,
        "max_steps": 1,
        "device": "cpu",
    }
    base.update(updates)
    return UnifiedCampaignConfig(**base)


def test_plan_materialises_every_requested_catalog_game_pair(tmp_path: Path) -> None:
    config = _config(tmp_path, seeds=(1,), holdout_size=0)
    plan = build_campaign_plan(config)
    assert len(plan) == len(build_catalog()) * len(known_games())
    assert len({(row["game"], row["candidate_id"]) for row in plan}) == len(plan)


@pytest.mark.parametrize("game", known_games())
def test_baseline_only_campaign_runs_every_required_metric_and_seal(
    tmp_path: Path, game: str
) -> None:
    output = tmp_path / game
    config = _config(
        tmp_path,
        output_dir=output,
        games=(game,),
        model_ids=(),
    )
    summary = run_unified_campaign({game: _synthetic(game)}, config)
    assert summary["matrix_complete"] is True
    assert summary["expected_model_game_pairs"] == 0
    assert summary["holdout_evaluated"] is False
    assert summary["prospective_evaluated"] is False
    baselines = [row for row in summary["results"] if row["source"] == "baseline"]
    assert {row["candidate_id"] for row in baselines} == {
        f"baseline:{name}" for name in REQUIRED_BASELINE_IDS
    }
    assert all(row["status"] == "SUCCEEDED" for row in baselines)
    for row in baselines:
        assert set(row["seed_summary"]) == set(REQUIRED_POINT_METRICS)
        for seed_result in row["seed_results"]:
            lock = Path(seed_result["prediction_lock"]["path"])
            payload = json.loads(lock.read_text(encoding="utf-8"))
            assert payload["actuals_known"] is False
            assert payload["predictions"]
    assert (output / "SHA256SUMS").is_file()


def test_candidate_bridge_executes_logistic_for_digit_and_select_games(tmp_path: Path) -> None:
    games = ("numbers3", "loto7")
    config = _config(
        tmp_path,
        games=games,
        model_ids=("logistic",),
        seeds=(1,),
    )
    summary = run_unified_campaign({game: _synthetic(game) for game in games}, config)
    rows = [row for row in summary["results"] if row["source"] == "catalog"]
    assert len(rows) == 2
    assert all(row["status"] == "SUCCEEDED" for row in rows)
    assert all(row["seed_summary"]["hit_at_1"]["count"] == 1 for row in rows)


def test_non_standalone_reconciliation_is_retained_in_matrix(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        games=("loto7",),
        model_ids=("hf-bottomup",),
        seeds=(1,),
    )
    summary = run_unified_campaign({"loto7": _synthetic("loto7")}, config)
    row = next(row for row in summary["results"] if row["source"] == "catalog")
    assert row["status"] == "NON_STANDALONE_METHOD"
    assert summary["matrix_complete"] is True
    assert summary["observed_model_game_pairs"] == 1


def test_output_directory_is_immutable(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        games=("numbers3",),
        model_ids=(),
        seeds=(1,),
    )
    frames = {"numbers3": _synthetic("numbers3")}
    run_unified_campaign(frames, config)
    with pytest.raises(FileExistsError, match="refusing to reuse"):
        run_unified_campaign(frames, config)

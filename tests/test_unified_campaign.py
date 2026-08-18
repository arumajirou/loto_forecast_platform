from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from loto.evaluation.metric_registry import REQUIRED_BASELINE_IDS, REQUIRED_POINT_METRICS
from loto.evaluation.unified_campaign import (
    UnifiedCampaignConfig,
    _decode_candidate_probability_matrix,
    build_campaign_plan,
    run_unified_campaign,
)
from loto.game.geometry import geometry_for, known_games


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


def test_plan_materialises_every_requested_unified_game_pair(tmp_path: Path) -> None:
    config = _config(tmp_path, seeds=(1,), holdout_size=0)
    plan = build_campaign_plan(config)
    assert len(plan) == 250 * len(known_games())
    assert len({(row["game"], row["candidate_id"]) for row in plan}) == len(plan)
    assert len({row["candidate_id"] for row in plan}) == 250
    assert sum(row["library"] == "probabilistic" for row in plan) == 76 * len(known_games())


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
            metadata = seed_result["runtime_samples"][0]["metadata"]
            assert metadata["decoder_id"].startswith("baseline-")
            assert metadata["distribution_source"] == "baseline_native"
    assert (output / "SHA256SUMS").is_file()


def test_probability_matrix_routing_uses_family_specific_within_tau_decoders() -> None:
    digit_geometry = geometry_for("numbers3")
    digit_row = np.asarray([0.01, 0.01, 0.01, 0.24, 0.20, 0.23, 0.01, 0.01, 0.01, 0.27])
    digit_matrix = np.vstack([digit_row, digit_row, digit_row])
    digit_prediction, digit_metadata = _decode_candidate_probability_matrix(
        digit_matrix,
        digit_geometry,
        tau=1,
    )
    assert digit_prediction.tolist() == [4, 4, 4]
    assert digit_metadata == {
        "distribution_source": "slot_binary_candidate_probabilities",
        "distribution_adapter_id": "row-normalized-slot-binary-probability-v1",
        "decoder_id": "within-tau-independent-slot-v1",
        "decoder_objective": "within_tau",
        "tau": 1,
    }

    select_geometry = geometry_for("mini")
    select_matrix = np.ones((select_geometry.positions, select_geometry.universe_size), dtype=float)
    select_prediction, select_metadata = _decode_candidate_probability_matrix(
        select_matrix,
        select_geometry,
        tau=1,
    )
    select_geometry.validate_outcome(select_prediction.tolist())
    assert select_metadata["decoder_id"] == "within-tau-constrained-dp-v1"
    assert select_metadata["distribution_adapter_id"] == "row-normalized-slot-binary-probability-v1"
    assert select_metadata["decoder_objective"] == "within_tau"


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

    by_game = {row["game"]: row for row in rows}
    digit_metadata = by_game["numbers3"]["seed_results"][0]["runtime_samples"][0]["metadata"]
    select_metadata = by_game["loto7"]["seed_results"][0]["runtime_samples"][0]["metadata"]
    assert digit_metadata["decoder_id"] == "within-tau-independent-slot-v1"
    assert select_metadata["decoder_id"] == "within-tau-constrained-dp-v1"
    for metadata in (digit_metadata, select_metadata):
        assert metadata["distribution_source"] == "slot_binary_candidate_probabilities"
        assert metadata["distribution_adapter_id"] == "row-normalized-slot-binary-probability-v1"
        assert metadata["decoder_objective"] == "within_tau"
        assert metadata["tau"] == 1


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


def test_loto3_campaign_plan_only_is_wired(capsys: pytest.CaptureFixture[str]) -> None:
    from loto.cli_v3 import build_parser

    args = build_parser().parse_args(
        [
            "campaign",
            "--output",
            "unused",
            "--games",
            "numbers3",
            "--models",
            "logistic",
            "--seeds",
            "1",
            "--git-commit",
            "1" * 40,
            "--plan-only",
        ]
    )
    assert args.func(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PLANNED"
    assert payload["model_game_pairs"] == 1
    assert payload["plan"][0]["candidate_id"] == "logistic"


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

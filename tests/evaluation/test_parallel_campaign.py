from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from loto.evaluation.parallel_campaign import cpu_sets, run_parallel_unified_campaign
from loto.evaluation.unified_campaign import UnifiedCampaignConfig
from loto.game.geometry import geometry_for


def _synthetic(game: str, rows: int, seed: int = 7) -> pd.DataFrame:
    geometry = geometry_for(game)
    rng = np.random.default_rng(seed)
    universe = np.arange(geometry.value_min, geometry.value_max + 1)
    payload = []
    for draw in range(rows):
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


def test_cpu_sets_are_non_empty_and_disjoint() -> None:
    sets = cpu_sets(3, 0)
    assert sets
    assert all(item for item in sets)
    flattened = [cpu for item in sets for cpu in item]
    assert len(flattened) == len(set(flattened))


def test_parallel_campaign_writes_complete_matrix(tmp_path: Path) -> None:
    games = ("numbers3", "loto7")
    frames = {game: _synthetic(game, 24) for game in games}
    output = tmp_path / "parallel"
    config = UnifiedCampaignConfig(
        output_dir=output,
        git_commit="0" * 40,
        games=games,
        model_ids=("logistic",),
        seeds=(1,),
        folds=1,
        test_size=2,
        min_train_size=12,
        holdout_size=4,
        device="cpu",
    )

    result = run_parallel_unified_campaign(frames, config, workers=2, reserve_cpus=0)

    assert result["matrix_complete"] is True
    assert result["expected_model_game_pairs"] == 2
    assert result["observed_model_game_pairs"] == 2
    assert result["execution_mode"] == "parallel_by_game"
    assert (output / "campaign_summary.json").is_file()
    assert (output / "model_game_results.csv").is_file()
    assert (output / "SHA256SUMS").is_file()
    assert (output / "games" / "numbers3" / "campaign_summary.json").is_file()
    assert (output / "games" / "loto7" / "campaign_summary.json").is_file()

    progress = json.loads((output / "progress.json").read_text(encoding="utf-8"))
    assert progress["games_completed"] == 2
    assert progress["model_game_pairs_completed"] == 2
    assert progress["matrix_complete"] is True

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from loto.game.geometry import known_games
from loto.statsforecast.real_game_campaign import (
    build_lane_matrix,
    load_normalized_frames,
    primary_univariate_entries,
)
from loto.statsforecast.real_game_preflight import statsforecast_entries


def test_primary_lane_inventory_is_39_of_41() -> None:
    entries = statsforecast_entries()
    primary = primary_univariate_entries(entries)

    assert len(entries) == 41
    assert len(primary) == 39
    assert {entry.class_name for entry in entries if entry not in primary} == {
        "NaNModel",
        "SklearnModel",
    }


def test_lane_matrix_preserves_all_41_by_6_rows() -> None:
    games = tuple(known_games())
    rows = build_lane_matrix(games, statsforecast_entries())

    assert len(games) == 6
    assert len(rows) == 246
    assert len({(row["game"], row["model_id"]) for row in rows}) == 246
    assert sum(row["planned_status"] == "EVALUATE_PRIMARY" for row in rows) == 234
    assert sum(row["planned_status"] == "DEFER_TO_EXOGENOUS_LANE" for row in rows) == 6
    assert sum(row["planned_status"] == "EXPECTED_NEGATIVE_CONTROL" for row in rows) == 6


def test_load_normalized_frames_accepts_acquisition_layout(tmp_path: Path) -> None:
    games = ("numbers3", "loto7")
    for game in games:
        path = tmp_path / game / "normalized" / f"{game}.csv"
        path.parent.mkdir(parents=True)
        pd.DataFrame({"draw_no": [1], "n1": [1]}).to_csv(path, index=False)

    frames = load_normalized_frames(tmp_path, games)

    assert tuple(frames) == games
    assert frames["numbers3"]["draw_no"].tolist() == [1]
    assert frames["loto7"]["n1"].tolist() == [1]


def test_load_normalized_frames_accepts_flat_layout(tmp_path: Path) -> None:
    path = tmp_path / "numbers4.csv"
    pd.DataFrame({"draw_no": [1], "n1": [4]}).to_csv(path, index=False)

    frames = load_normalized_frames(tmp_path, ("numbers4",))

    assert frames["numbers4"]["n1"].tolist() == [4]


def test_load_normalized_frames_fails_visible_for_missing_game(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="missing normalized CSV for mini"):
        load_normalized_frames(tmp_path, ("mini",))

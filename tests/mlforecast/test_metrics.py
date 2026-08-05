from __future__ import annotations

import pandas as pd

from loto.mlforecast.metrics import evaluate_prediction, make_baseline_predictions


def test_metrics_include_position_and_all_position_hit() -> None:
    actual = pd.DataFrame(
        {
            "unique_id": ["p1", "p2", "p1", "p2"],
            "ds": [1, 1, 2, 2],
            "y": [1.0, 5.0, 2.0, 6.0],
        }
    )
    predicted = pd.DataFrame(
        {
            "unique_id": ["p1", "p2", "p1", "p2"],
            "ds": [1, 1, 2, 2],
            "ridge": [2.0, 7.0, 2.5, 6.0],
        }
    )
    overall, positions = evaluate_prediction(
        actual,
        predicted,
        prediction_col="ridge",
        id_col="unique_id",
        time_col="ds",
        target_col="y",
    )
    assert overall["hit_at_1"] == 0.75
    assert overall["all_position_hit_at_1"] == 0.5
    assert set(positions["unique_id"]) == {"p1", "p2"}


def test_baselines_are_key_aligned_and_deterministic() -> None:
    train = pd.DataFrame(
        {
            "unique_id": ["p1"] * 4,
            "ds": [1, 2, 3, 4],
            "y": [1.0, 1.0, 2.0, 3.0],
        }
    )
    future = pd.DataFrame({"unique_id": ["p1", "p1"], "ds": [5, 6], "y": [4.0, 5.0]})
    first = make_baseline_predictions(
        train,
        future,
        id_col="unique_id",
        time_col="ds",
        target_col="y",
        seed=1,
        fixed_value=4.5,
        season_length=2,
    )
    second = make_baseline_predictions(
        train,
        future,
        id_col="unique_id",
        time_col="ds",
        target_col="y",
        seed=1,
        fixed_value=4.5,
        season_length=2,
    )
    assert first["baseline_random"].equals(second["baseline_random"])
    assert first["baseline_fixed"]["baseline_fixed"].tolist() == [4.5, 4.5]

from __future__ import annotations

import numpy as np
import pandas as pd

from loto.auto_campaign.prospective_scoring_metrics import (
    _add_combined_local_candidates,
    _baseline_comparison,
    _score_candidates,
    _seed_summary,
)

NUMBER_COLUMNS = ["P1", "P2", "P3", "P4", "P5"]


def _actuals() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "draw_id": "D4",
                "draw_index": 4,
                "P1": 4,
                "P2": 8,
                "P3": 13,
                "P4": 23,
                "P5": 31,
            }
        ]
    )


def _complete_candidate(source_type: str = "model") -> pd.DataFrame:
    values = [4.1, 8.4, 12.2, 23.7, 30.4]
    rows = []
    for unique_id, prediction in zip(NUMBER_COLUMNS, values, strict=True):
        rows.append(
            {
                "candidate_id": "candidate-1",
                "task_path": "task-1",
                "source_type": source_type,
                "model_name": "AutoTFT" if source_type == "model" else None,
                "baseline_name": None if source_type == "model" else "last",
                "track": "u_shared" if source_type == "model" else "baseline",
                "position": None,
                "seed": 1 if source_type == "model" else None,
                "backend": "ray" if source_type == "model" else "numpy",
                "config_index": None,
                "ds": 4,
                "unique_id": unique_id,
                "prediction": prediction,
            }
        )
    return pd.DataFrame(rows)


def test_complete_candidate_reports_priority_and_all_position_metrics() -> None:
    metrics, positions, scored = _score_candidates(
        _complete_candidate(),
        _actuals(),
        number_columns=NUMBER_COLUMNS,
        expected_ds=[4],
    )

    reconciled = metrics[metrics["variant"].eq("reconciled")].iloc[0]
    assert reconciled["hit_pm1"] == 1.0
    assert reconciled["all_positions_hit_pm1"] == 1.0
    assert reconciled["mae"] >= 0.0
    assert reconciled["mse"] >= 0.0
    assert reconciled["rmse"] >= 0.0
    assert set(positions["unique_id"]) == set(NUMBER_COLUMNS)
    assert scored["hit_pm1"].all()


def test_local_candidates_are_combined_only_when_all_positions_exist() -> None:
    parts = []
    for position, unique_id in enumerate(NUMBER_COLUMNS, start=1):
        row = _complete_candidate().iloc[[position - 1]].copy()
        row["candidate_id"] = f"local-{position}"
        row["task_path"] = f"task-local-{position}"
        row["track"] = "u_local"
        row["position"] = position
        parts.append(row)

    combined = _add_combined_local_candidates(
        pd.concat(parts, ignore_index=True),
        NUMBER_COLUMNS,
    )

    combined_rows = combined[combined["track"].eq("u_local_combined")]
    assert len(combined_rows) == 5
    assert combined_rows["candidate_id"].nunique() == 1
    assert set(combined_rows["unique_id"]) == set(NUMBER_COLUMNS)


def test_seed_ranking_prioritizes_hit_pm1_then_all_positions() -> None:
    model_metrics, _, _ = _score_candidates(
        _complete_candidate("model"),
        _actuals(),
        number_columns=NUMBER_COLUMNS,
        expected_ds=[4],
    )
    baseline_frame = _complete_candidate("baseline")
    baseline_frame["prediction"] = np.asarray([1, 5, 10, 20, 28], dtype=float)
    baseline_metrics, _, _ = _score_candidates(
        baseline_frame,
        _actuals(),
        number_columns=NUMBER_COLUMNS,
        expected_ds=[4],
    )

    summary, ranking = _seed_summary(
        pd.concat([model_metrics, baseline_metrics], ignore_index=True)
    )
    comparison, champion = _baseline_comparison(ranking)

    assert not summary.empty
    assert ranking.iloc[0]["source_type"] == "model"
    assert champion is not None
    assert champion["model_name"] == "AutoTFT"
    assert comparison.iloc[0]["hit_pm1_delta"] > 0.0

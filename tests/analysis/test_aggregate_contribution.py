from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

MODULE = Path(__file__).parents[2] / "scripts/analysis/aggregate_contribution.py"
SPEC = importlib.util.spec_from_file_location("aggregate_contribution", MODULE)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_zero_baseline_does_not_warn_or_crash():
    frame = pd.DataFrame(
        [
            {
                "model_id": "m",
                "fold": fold,
                "seed": 42,
                "condition": "full_exogenous",
                "feature_group": "all",
                "position_mae": 1.0,
                "row_within_1": 0.0,
            }
            for fold in range(30)
        ]
        + [
            {
                "model_id": "m",
                "fold": fold,
                "seed": 42,
                "condition": "drop_group",
                "feature_group": "frequency",
                "position_mae": 2.0,
                "row_within_1": 0.0,
            }
            for fold in range(30)
        ]
    )

    result = mod.aggregate_contributions(frame)
    row = result[result["metric"].eq("row_within_1")].iloc[0]
    assert row["relative_contribution_defined_rows"] == 0
    assert pd.isna(row["relative_contribution_pct"])


def test_lower_is_better_contribution_sign():
    frame = pd.DataFrame(
        [
            {
                "model_id": "m",
                "fold": fold,
                "seed": 42,
                "condition": "full_exogenous",
                "feature_group": "all",
                "position_mae": 1.0,
            }
            for fold in range(30)
        ]
        + [
            {
                "model_id": "m",
                "fold": fold,
                "seed": 42,
                "condition": "drop_group",
                "feature_group": "frequency",
                "position_mae": 2.0,
            }
            for fold in range(30)
        ]
    )

    result = mod.aggregate_contributions(frame)
    assert np.isclose(result.iloc[0]["absolute_contribution"], 1.0)
    assert result.iloc[0]["ci95_low"] > 0

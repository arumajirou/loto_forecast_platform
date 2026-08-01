from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

MODULE = Path(__file__).parents[2] / "scripts/analysis/aggregate_multiseed_contribution.py"
SPEC = importlib.util.spec_from_file_location(
    "aggregate_multiseed_contribution",
    MODULE,
)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def _frame() -> pd.DataFrame:
    rows = []
    for seed in (42, 123, 2026):
        for fold in range(1, 6):
            rows.extend(
                [
                    {
                        "model_id": "m",
                        "fold": fold,
                        "seed": seed,
                        "condition": "full_exogenous",
                        "feature_group": "all",
                        "position_mae": 1.0,
                        "element_within_1": 0.5,
                    },
                    {
                        "model_id": "m",
                        "fold": fold,
                        "seed": seed,
                        "condition": "drop_group",
                        "feature_group": "frequency",
                        "position_mae": 2.0,
                        "element_within_1": 0.2,
                    },
                ]
            )
    return pd.DataFrame(rows)


def test_multiseed_cluster_summary():
    summary, seed_detail = mod.aggregate_multiseed(
        _frame(),
        bootstrap_iterations=1_000,
    )

    mae = summary[summary["metric"].eq("position_mae")].iloc[0]
    assert mae["absolute_contribution"] == 1.0
    assert mae["unique_folds"] == 5
    assert mae["unique_seeds"] == 3
    assert mae["all_seeds_positive"]
    assert mae["cluster_ci95_low"] > 0
    assert len(seed_detail) == 6


def test_validate_dynamic_expected_rows(tmp_path):
    frame = _frame()
    one_seed = frame[frame["seed"].eq(42)]
    path = tmp_path / "ablation_results.csv"
    one_seed.to_csv(path, index=False)

    manifest = mod.validate_seed_frame(one_seed, source=path)
    assert manifest["expected_rows"] == 10
    assert manifest["rows"] == 10

    with pytest.raises(ValueError, match="expected"):
        mod.validate_seed_frame(
            one_seed.iloc[:-1],
            source=path,
        )

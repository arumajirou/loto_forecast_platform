from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


MODULE = (
    Path(__file__).parents[2]
    / "scripts/analysis/run_candidate_exog_robustness.py"
)
SPEC = importlib.util.spec_from_file_location(
    "run_candidate_exog_robustness",
    MODULE,
)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_conditions_are_unique_and_hashed():
    conditions = mod.build_conditions()
    keys = [
        (item["condition"], item["feature_group"])
        for item in conditions
    ]
    assert len(keys) == len(set(keys))
    assert len(conditions) == 12
    assert all(len(item["feature_set_hash"]) == 64 for item in conditions)


def test_feature_set_hash_is_order_independent():
    left = mod.feature_set_hash(["a", "b", "c"])
    right = mod.feature_set_hash(["c", "a", "b"])
    assert left == right


def test_block_permutation_preserves_values_and_blocks():
    frame = pd.DataFrame(
        {
            "x": np.arange(12),
            "y": np.arange(100, 112),
        }
    )
    output = mod.block_permute(
        frame,
        columns=["x", "y"],
        block_size=3,
        seed=42,
    )

    assert sorted(output["x"].tolist()) == list(range(12))
    assert sorted(output["y"].tolist()) == list(range(100, 112))

    for start in range(0, len(output), 3):
        block = output.iloc[start : start + 3]["x"].to_numpy()
        assert np.all(np.diff(block) == 1)

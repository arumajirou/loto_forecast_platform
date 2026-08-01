from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

ANALYSIS = Path(__file__).parents[2] / "scripts/analysis"
sys.path.insert(0, str(ANALYSIS))

MODULE = ANALYSIS / "run_candidate_exog_robustness_v21.py"
SPEC = importlib.util.spec_from_file_location("robustness_v21", MODULE)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def _frame(draws: int = 4) -> pd.DataFrame:
    rows = []
    for draw in range(1, draws + 1):
        for candidate in range(1, 38):
            rows.append(
                {
                    "draw_no": draw,
                    "candidate_number": candidate,
                    "candidate_scaled": candidate / 37,
                    "candidate_is_even": candidate % 2 == 0,
                    "candidate_mod3": candidate % 3,
                    "candidate_mod10": candidate % 10,
                    "candidate_is_prime": candidate in {2, 3, 5, 7},
                    "freq_w5": draw * 100 + candidate,
                    "freq_w10": draw * 200 + candidate,
                    "freq_w20": draw * 300 + candidate,
                    "freq_w30": draw * 400 + candidate,
                    "freq_w50": draw * 500 + candidate,
                    "freq_w100": draw * 600 + candidate,
                    "freq_all": draw * 700 + candidate,
                    "freq_exp": draw * 800 + candidate,
                    "gap_draws": draw * 900 + candidate,
                    "selected": int(candidate <= 7),
                }
            )
    return pd.DataFrame(rows)


def test_identity_permutation_changes_query():
    frame = _frame(1)
    condition = {
        "condition": "group_permutation",
        "feature_group": "candidate_identity",
        "feature_columns": [
            *mod.IDENTITY_FEATURES,
            *mod.FREQUENCY_FEATURES,
            *mod.GAP_FEATURES,
        ],
        "transform": "within_draw_candidate_permutation",
    }
    transformed = mod.apply_transform(
        frame,
        condition=condition,
        seed=42,
    )
    assert mod.transform_changed(
        frame,
        transformed,
        mod.IDENTITY_FEATURES,
    )


def test_circular_shift_changes_historical_features():
    frame = _frame(4)
    condition = {
        "condition": "group_permutation",
        "feature_group": "historical_frequency",
        "feature_columns": [
            *mod.IDENTITY_FEATURES,
            *mod.FREQUENCY_FEATURES,
            *mod.GAP_FEATURES,
        ],
        "transform": "circular_draw_shift",
    }
    transformed = mod.apply_transform(
        frame,
        condition=condition,
        seed=42,
    )
    assert mod.transform_changed(
        frame,
        transformed,
        mod.FREQUENCY_FEATURES,
    )


def test_protocol_hash_distinguishes_transform():
    conditions = mod.build_conditions()
    full = next(item for item in conditions if item["condition"] == "full_exogenous")
    permuted = next(
        item
        for item in conditions
        if item["condition"] == "group_permutation"
        and item["feature_group"] == "historical_frequency"
    )

    assert mod.feature_set_hash(full["feature_columns"]) == mod.feature_set_hash(
        permuted["feature_columns"]
    )
    assert mod.protocol_hash(
        full,
        seed=42,
    ) != mod.protocol_hash(permuted, seed=42)


def test_single_draw_query_uses_train_source_pool():
    train = _frame(4)
    query = train[train["draw_no"].eq(4)].copy()
    condition = {
        "condition": "group_permutation",
        "feature_group": "historical_frequency",
        "feature_columns": [
            *mod.IDENTITY_FEATURES,
            *mod.FREQUENCY_FEATURES,
            *mod.GAP_FEATURES,
        ],
        "transform": "circular_draw_shift",
    }

    transformed = mod.apply_transform(
        query,
        condition=condition,
        seed=43,
        source_pool=train[train["draw_no"].lt(4)],
    )

    assert mod.transform_changed(
        query,
        transformed,
        mod.FREQUENCY_FEATURES,
    )

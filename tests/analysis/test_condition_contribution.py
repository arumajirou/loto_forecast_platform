from __future__ import annotations

import numpy as np
import pandas as pd

from loto.analysis.contribution import Comparison, adjust_pvalues, paired_summary


def frame() -> pd.DataFrame:
    rows = []
    for seed in (1, 2, 3):
        for fold in range(10):
            rows.append({"model_id": "m", "fold": fold, "seed": seed, "condition": "full_exogenous", "feature_group": "frequency", "brier": 0.10})
            rows.append({"model_id": "m", "fold": fold, "seed": seed, "condition": "drop_group", "feature_group": "frequency", "brier": 0.20})
    return pd.DataFrame(rows)


def test_paired_cluster_summary_and_corrections() -> None:
    result = paired_summary(frame(), comparison=Comparison("drop", "full_exogenous", "drop_group"), metric="brier", bootstrap_iterations=500)
    assert len(result) == 1
    row = result.iloc[0]
    assert row["absolute_contribution"] > 0
    assert row["cluster_ci95_low"] > 0
    assert row["all_seeds_positive"]
    assert row["positive_fold_rate"] == 1.0
    assert row["pvalue_holm"] < 0.05


def test_multiple_comparison_adjustment_monotonic() -> None:
    pvalues = [0.001, 0.01, 0.2]
    holm = adjust_pvalues(pvalues, "holm")
    bh = adjust_pvalues(pvalues, "bh")
    assert np.all(np.asarray(holm) >= pvalues)
    assert np.all(np.asarray(bh) >= pvalues)

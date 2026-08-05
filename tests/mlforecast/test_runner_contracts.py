from __future__ import annotations

import pandas as pd
import pytest

from loto.mlforecast.contracts import MLForecastRunConfig
from loto.mlforecast.runner import chronological_split, validate_panel


def panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "unique_id": ["p1"] * 5 + ["p2"] * 5,
            "ds": list(range(1, 6)) * 2,
            "y": list(range(5)) + list(range(5, 10)),
        }
    )


def test_chronological_split_keeps_future_out_of_train() -> None:
    config = MLForecastRunConfig(h=2, holdout_size=2)
    validated = validate_panel(panel(), config)
    train, holdout = chronological_split(validated, config)
    for series_id in ["p1", "p2"]:
        assert train.loc[train.unique_id == series_id, "ds"].max() == 3
        assert holdout.loc[holdout.unique_id == series_id, "ds"].min() == 4


def test_duplicates_fail_closed() -> None:
    config = MLForecastRunConfig()
    duplicated = pd.concat([panel(), panel().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        validate_panel(duplicated, config)

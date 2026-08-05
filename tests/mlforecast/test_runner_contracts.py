from __future__ import annotations

import pandas as pd
import pytest

from loto.mlforecast.contracts import MLForecastRunConfig
from loto.mlforecast.data import chronological_split, validate_future_features, validate_panel
from loto.mlforecast.runner import RunResult


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


def test_out_of_order_input_fails_closed() -> None:
    config = MLForecastRunConfig()
    out_of_order = panel().copy()
    out_of_order.loc[[0, 1], "ds"] = [2, 1]
    with pytest.raises(ValueError, match="not chronologically ordered"):
        validate_panel(out_of_order, config)


def test_unclassified_exogenous_column_fails_closed() -> None:
    config = MLForecastRunConfig()
    frame = panel().assign(weather=1.0)
    with pytest.raises(ValueError, match="unclassified"):
        validate_panel(frame, config)


def test_static_feature_must_be_constant_per_series() -> None:
    config = MLForecastRunConfig(static_features=["region"])
    frame = panel().assign(region=["a", "b", "a", "a", "a"] + ["c"] * 5)
    with pytest.raises(ValueError, match="changes within series"):
        validate_panel(frame, config)


def test_known_future_feature_and_exact_keys_are_accepted() -> None:
    config = MLForecastRunConfig(known_future_features=["event"])
    validated = validate_panel(panel().assign(event=0), config)
    assert "event" in validated
    expected = pd.DataFrame({"unique_id": ["p1", "p2"], "ds": [6, 6]})
    future = expected.assign(event=[1, 0])
    result = validate_future_features(future, expected_keys=expected, config=config)
    assert result is not None
    assert result["event"].tolist() == [1, 0]


def test_future_keys_must_match_exact_horizon() -> None:
    config = MLForecastRunConfig(known_future_features=["event"])
    expected = pd.DataFrame({"unique_id": ["p1", "p2"], "ds": [6, 6]})
    wrong = pd.DataFrame({"unique_id": ["p1", "p2"], "ds": [6, 7], "event": [1, 0]})
    with pytest.raises(ValueError, match="do not match"):
        validate_future_features(wrong, expected_keys=expected, config=config)


def test_run_result_is_constructible(tmp_path) -> None:
    metrics = pd.DataFrame({"hit_at_1": [1.0]})
    result = RunResult(run_id="run-1", run_dir=tmp_path, status="EXECUTED", metrics=metrics)
    assert result.run_id == "run-1"
    assert result.metrics.equals(metrics)

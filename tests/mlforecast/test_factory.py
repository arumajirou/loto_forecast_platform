from __future__ import annotations

import sys
import types

import pandas as pd

from loto.mlforecast.contracts import AutoConfig, CoreConfig, SearchParameter
from loto.mlforecast.factory import (
    build_auto_forecast,
    build_core_forecast,
    build_search_space,
    hit_at_1_objective,
)


class FakeTrial:
    def suggest_float(self, name, low, high, **kwargs):
        assert name == "alpha"
        assert kwargs["log"] is True
        return (low + high) / 2


def test_declarative_search_space_builds_callable() -> None:
    config = build_search_space(
        {"alpha": SearchParameter(kind="float", low=0.001, high=10.0, log=True)}
    )
    assert config is not None
    result = config(FakeTrial())
    assert result["alpha"] > 0


def test_build_auto_forecast_supports_all_selected_models(monkeypatch) -> None:
    captured = {}

    class FakeAutoModel:
        def __init__(self, config=None):
            self.config = config

    class FakeAutoMLForecast:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_auto = types.SimpleNamespace(
        AutoLightGBM=FakeAutoModel,
        AutoXGBoost=FakeAutoModel,
        AutoCatboost=FakeAutoModel,
        AutoLinearRegression=FakeAutoModel,
        AutoRidge=FakeAutoModel,
        AutoLasso=FakeAutoModel,
        AutoElasticNet=FakeAutoModel,
        AutoRandomForest=FakeAutoModel,
        AutoMLForecast=FakeAutoMLForecast,
    )
    monkeypatch.setitem(sys.modules, "mlforecast", types.SimpleNamespace(auto=fake_auto))

    selected = ["AutoRidge", "AutoElasticNet", "AutoRandomForest"]
    result = build_auto_forecast(
        AutoConfig(models=selected, season_length=1),
        static_features=["region"],
    )

    assert isinstance(result, FakeAutoMLForecast)
    assert list(captured["models"]) == selected
    assert captured["freq"] == 1
    assert captured["reuse_cv_splits"] is True
    assert captured["fit_config"](object())["static_features"] == ["region"]


def test_core_constructor_uses_only_frozen_arguments(monkeypatch) -> None:
    captured = {}

    class FakeMLForecast:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "mlforecast", types.SimpleNamespace(MLForecast=FakeMLForecast))
    result = build_core_forecast(CoreConfig(models=["ridge"]), seed=1)

    assert isinstance(result, FakeMLForecast)
    assert set(captured) == {
        "models",
        "freq",
        "lags",
        "lag_transforms",
        "date_features",
        "num_threads",
        "target_transforms",
        "date_features_as_dummies",
        "drop_auxiliary_columns",
    }


def test_hit_at_1_objective_accepts_upstream_keywords() -> None:
    validation = pd.DataFrame({"y": [0.0, 0.0], "model": [1.01, 1.01]})
    result = hit_at_1_objective(
        validation,
        train_df=validation,
        weight_col="sample_weight",
    )
    assert 2.0 < result < 3.0


def test_hit_at_1_objective_prioritizes_miss_count_over_mae() -> None:
    actual = pd.DataFrame({"y": [0.0, 0.0], "model": [1.01, 1.01]})
    one_miss = hit_at_1_objective(actual, actual)
    huge_mae_but_hits = pd.DataFrame({"y": [1_000_000.0], "model": [1_000_001.0]})
    zero_misses = hit_at_1_objective(huge_mae_but_hits, huge_mae_but_hits)
    assert zero_misses < one_miss

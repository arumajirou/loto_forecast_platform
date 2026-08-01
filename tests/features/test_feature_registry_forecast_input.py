from __future__ import annotations

import pandas as pd
import pytest

from loto.features.point_in_time import point_in_time_join
from loto.features.registry import FeatureRegistry
from loto.features.spec import Availability, FeatureSpec
from loto.models.exogenous_adapters import mlforecast_predict_kwargs, neuralforecast_payload, timesfm_covariates
from loto.models.forecast_input import ForecastInput


def registry() -> FeatureRegistry:
    value = FeatureRegistry()
    value.register(FeatureSpec("freq", "float64", Availability.HISTORICAL, "features"))
    value.register(FeatureSpec("weekday", "int64", Availability.FUTURE_KNOWN, "calendar"))
    value.register(FeatureSpec("game", "string", Availability.STATIC, "contract"))
    return value


def test_manifest_hash_is_deterministic() -> None:
    assert registry().manifest()["feature_set_hash"] == registry().manifest()["feature_set_hash"]


def test_target_cannot_be_registered_as_feature() -> None:
    with pytest.raises(ValueError, match="target columns"):
        ForecastInput.build(
            history=pd.DataFrame({"selected": [0, 1]}),
            registry=registry_with_target(),
            target_columns=("selected",),
        )


def registry_with_target() -> FeatureRegistry:
    value = registry()
    value.register(FeatureSpec("selected", "int64", Availability.HISTORICAL, "bad"))
    return value


def test_point_in_time_join_never_uses_future() -> None:
    observations = pd.DataFrame({"id": [1, 1], "at": ["2026-01-02", "2026-01-04"]})
    features = pd.DataFrame({"id": [1, 1], "known_at": ["2026-01-01", "2026-01-03"], "value": [10, 20]})
    joined = point_in_time_join(observations, features, entity_keys=("id",), observation_time="at", feature_time="known_at")
    assert joined["value"].tolist() == [10, 20]


def test_adapters_receive_real_exogenous_frames() -> None:
    future = pd.DataFrame({"weekday": [2]})
    historical = pd.DataFrame({"freq": [0.1, 0.2]})
    static = pd.DataFrame({"game": ["numbers3"]})
    inp = ForecastInput.build(
        history=pd.DataFrame({"y": [1, 2]}),
        registry=registry(),
        target_columns=("y",),
        historical_exogenous=historical,
        future_exogenous=future,
        static_exogenous=static,
    )
    payload = neuralforecast_payload(inp)
    assert payload.hist_exog_list == ("freq",)
    assert payload.futr_exog_list == ("weekday",)
    assert mlforecast_predict_kwargs(inp)["X_df"] is not None
    assert timesfm_covariates(inp)["dynamic_numerical_covariates"]["weekday"] == [2.0]

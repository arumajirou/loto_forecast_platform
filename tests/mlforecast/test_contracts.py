from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.mlforecast.contracts import (
    AUTO_MODEL_NAMES,
    AutoConfig,
    CoreConfig,
    MLForecastRunConfig,
    SearchParameter,
)


def test_all_eight_auto_models_are_accepted() -> None:
    config = AutoConfig(models=list(AUTO_MODEL_NAMES))
    assert tuple(config.models) == AUTO_MODEL_NAMES


def test_unknown_auto_model_fails_closed() -> None:
    with pytest.raises(ValidationError, match="unsupported AutoMLForecast models"):
        AutoConfig(models=["AutoUnknown"])


def test_search_parameter_contract() -> None:
    parameter = SearchParameter(kind="float", low=1e-4, high=1e-2, log=True)
    assert parameter.log is True
    with pytest.raises(ValidationError):
        SearchParameter(kind="categorical", choices=[])
    with pytest.raises(ValidationError, match="cannot define step"):
        SearchParameter(kind="float", low=0.1, high=1.0, log=True, step=0.1)


def test_holdout_horizon_must_match() -> None:
    with pytest.raises(ValidationError, match="h must equal holdout_size"):
        MLForecastRunConfig(h=2, holdout_size=1)


def test_runtime_version_is_frozen() -> None:
    assert MLForecastRunConfig().required_mlforecast_version == "1.0.31"
    with pytest.raises(ValidationError):
        MLForecastRunConfig(required_mlforecast_version="1.1.0")


def test_newer_unfrozen_arguments_fail_closed() -> None:
    for field in ("date_features_as_dummies", "drop_auxiliary_columns", "cache_train_df"):
        with pytest.raises(ValidationError):
            CoreConfig.model_validate({field: True})


def test_feature_declarations_are_disjoint() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        MLForecastRunConfig(static_features=["region"], known_future_features=["region"])

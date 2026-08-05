from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.mlforecast.contracts import (
    AUTO_MODEL_NAMES,
    AutoConfig,
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


def test_holdout_horizon_must_match() -> None:
    with pytest.raises(ValidationError, match="h must equal holdout_size"):
        MLForecastRunConfig(h=2, holdout_size=1)

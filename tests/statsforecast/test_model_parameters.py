from __future__ import annotations

from sklearn.linear_model import LinearRegression

from loto.statsforecast.certification_models import (
    resolve_parameters as certification_resolve_parameters,
)
from loto.statsforecast.model_parameters import (
    required_parameters,
    resolve_parameters,
)


class FakeARIMA:
    def __init__(self, order):
        self.order = order


class FakeSeasonalNaive:
    def __init__(self, season_length):
        self.season_length = season_length


class FakeUnknown:
    def __init__(self, required_unknown):
        self.required_unknown = required_unknown


class FakeSklearnModel:
    def __init__(self, model):
        self.model = model


def test_shared_api_uses_certification_resolver() -> None:
    assert resolve_parameters is certification_resolve_parameters


def test_required_parameters() -> None:
    assert required_parameters(FakeARIMA) == ("order",)


def test_shared_default_is_applied() -> None:
    params, unresolved = resolve_parameters("ARIMA", FakeARIMA, None)

    assert unresolved == ()
    assert params == {"order": (1, 0, 0)}


def test_override_wins_over_shared_default() -> None:
    params, unresolved = resolve_parameters(
        "SeasonalNaive",
        FakeSeasonalNaive,
        {"season_length": 12},
    )

    assert unresolved == ()
    assert params["season_length"] == 12


def test_unresolved_parameter_is_fail_visible() -> None:
    params, unresolved = resolve_parameters("Unknown", FakeUnknown, None)

    assert params == {}
    assert unresolved == ("required_unknown",)


def test_sklearn_model_gets_deterministic_estimator() -> None:
    params, unresolved = resolve_parameters("SklearnModel", FakeSklearnModel, None)

    assert unresolved == ()
    assert isinstance(params["model"], LinearRegression)

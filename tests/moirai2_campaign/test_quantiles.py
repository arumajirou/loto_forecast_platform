from __future__ import annotations

import numpy as np
import pytest

from loto.moirai2_campaign.quantiles import (
    QuantileValidationError,
    extract_native_quantiles,
    median_point_forecast,
)


class FakeForecast:
    def __init__(self, crossing: bool = False):
        self.crossing = crossing

    def quantile(self, level: float) -> np.ndarray:
        value = level
        if self.crossing and level == 0.6:
            value = 0.1
        return np.full((2, 3), value, dtype=float)


def test_all_native_quantiles_and_median_are_retained() -> None:
    quantiles = extract_native_quantiles(FakeForecast(), horizon=2, position_count=3)
    assert list(quantiles) == [f"{level / 10:.1f}" for level in range(1, 10)]
    assert median_point_forecast(quantiles) == [[0.5, 0.5, 0.5], [0.5, 0.5, 0.5]]


def test_quantile_crossing_fails_closed() -> None:
    with pytest.raises(QuantileValidationError, match="cross"):
        extract_native_quantiles(FakeForecast(crossing=True), horizon=2, position_count=3)


class NonFiniteForecast(FakeForecast):
    def quantile(self, level: float) -> np.ndarray:
        values = super().quantile(level)
        if level == 0.9:
            values[0, 0] = np.nan
        return values


def test_non_finite_native_quantile_fails_closed() -> None:
    with pytest.raises(QuantileValidationError, match="NaN or Inf"):
        extract_native_quantiles(NonFiniteForecast(), horizon=2, position_count=3)


def test_non_native_quantile_inventory_is_rejected() -> None:
    with pytest.raises(QuantileValidationError, match="native levels"):
        extract_native_quantiles(
            FakeForecast(),
            horizon=2,
            position_count=3,
            levels=(0.1, 0.5, 0.9),
        )

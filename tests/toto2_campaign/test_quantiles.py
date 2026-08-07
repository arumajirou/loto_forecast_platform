from __future__ import annotations

import numpy as np
import pytest

from loto.toto2_campaign.quantiles import extract_native_quantiles


def test_extract_native_quantiles_uses_q05_as_point() -> None:
    values = np.arange(9, dtype=np.float32)[:, None, None, None]
    result = extract_native_quantiles(values, expected_series=1, expected_horizon=1)
    assert result.point_forecast == [[4.0]]
    assert result.quantiles["q0.1"] == [[0.0]]
    assert result.quantiles["q0.9"] == [[8.0]]
    assert result.monotonic is True


def test_quantile_crossing_is_rejected() -> None:
    values = np.arange(9, dtype=np.float32)[:, None, None, None]
    values[4, 0, 0, 0] = 99.0
    with pytest.raises(ValueError, match="cross"):
        extract_native_quantiles(values, expected_series=1, expected_horizon=1)


def test_non_finite_output_is_rejected() -> None:
    values = np.arange(9, dtype=np.float32)[:, None, None, None]
    values[0, 0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        extract_native_quantiles(values, expected_series=1, expected_horizon=1)

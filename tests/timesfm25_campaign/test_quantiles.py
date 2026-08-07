from __future__ import annotations

import numpy as np
import pytest

from loto.timesfm25_campaign.quantiles import split_native_outputs


def full_output(series: int, horizon: int) -> np.ndarray:
    output = np.empty((series, horizon, 10), dtype=float)
    output[:, :, 0] = 5.5
    for index in range(1, 10):
        output[:, :, index] = float(index)
    return output


def test_native_mean_median_and_quantiles_are_separated() -> None:
    full = full_output(3, 5)
    point = full[:, :, 5]
    median, mean, quantiles = split_native_outputs(point, full)
    assert median.shape == (3, 5)
    assert mean.shape == (3, 5)
    assert len(quantiles) == 9
    assert np.all(mean == 5.5)
    assert np.all(quantiles["0.5"] == point)


def test_non_finite_output_is_rejected() -> None:
    full = full_output(3, 1)
    full[0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="NaN or Inf"):
        split_native_outputs(full[:, :, 5], full)

from __future__ import annotations

import numpy as np
import pytest

from loto.tirex2_campaign.quantiles import (
    assert_future_mutation_invariance,
    normalize_forecast,
    point_forecast,
    quantile_mapping,
)


def test_normalize_forecast_preserves_full_horizon_and_quantiles() -> None:
    raw = np.arange(3 * 9 * 5, dtype=np.float64).reshape(3, 9, 5)
    normalized = normalize_forecast(raw, target_count=3, prediction_length=5)
    assert normalized.shape == (3, 9, 5)
    assert point_forecast(normalized) == raw[:, 4, :].tolist()
    assert len(quantile_mapping(normalized)) == 9


def test_normalize_forecast_rejects_truncated_horizon() -> None:
    raw = np.zeros((3, 9, 1), dtype=np.float64)
    with pytest.raises(ValueError, match="expected"):
        normalize_forecast(raw, target_count=3, prediction_length=2)


def test_normalize_forecast_rejects_crossing() -> None:
    raw = np.zeros((1, 9, 1), dtype=np.float64)
    raw[:, 5, :] = -1.0
    with pytest.raises(ValueError, match="crossing"):
        normalize_forecast(raw, target_count=1, prediction_length=1)


def test_future_mutation_invariance_passes_for_identical_predictions() -> None:
    assert_future_mutation_invariance([[1.0, 2.0]], [[1.0, 2.0]])


def test_future_mutation_invariance_fails_on_change() -> None:
    with pytest.raises(ValueError, match="FUTURE_MUTATION_INVARIANCE"):
        assert_future_mutation_invariance([[1.0]], [[2.0]])

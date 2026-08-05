from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from loto.adapters.tirex2.contracts import QUANTILE_LEVELS


def normalize_forecast(
    forecast: np.ndarray,
    *,
    target_count: int,
    prediction_length: int,
) -> np.ndarray:
    """Return a strict [target, quantile, horizon] float64 array."""
    array = np.asarray(forecast, dtype=np.float64)
    if array.ndim == 2 and target_count == 1:
        array = array[np.newaxis, :, :]
    expected = (target_count, len(QUANTILE_LEVELS), prediction_length)
    if array.shape != expected:
        raise ValueError(f"unexpected TiRex forecast shape: {array.shape}; expected {expected}")
    if not np.isfinite(array).all():
        raise ValueError("TiRex forecast contains non-finite values")
    if np.any(np.diff(array, axis=1) < 0):
        raise ValueError("TiRex forecast contains quantile crossing")
    return array


def quantile_mapping(array: np.ndarray) -> dict[str, list[list[float]]]:
    return {
        f"{level:.1f}": array[:, index, :].astype(float).tolist()
        for index, level in enumerate(QUANTILE_LEVELS)
    }


def point_forecast(array: np.ndarray) -> list[list[float]]:
    return array[:, 4, :].astype(float).tolist()


def assert_future_mutation_invariance(
    baseline: Sequence[Sequence[float]],
    mutated: Sequence[Sequence[float]],
    *,
    absolute_tolerance: float = 0.0,
) -> None:
    baseline_array = np.asarray(baseline, dtype=np.float64)
    mutated_array = np.asarray(mutated, dtype=np.float64)
    if baseline_array.shape != mutated_array.shape:
        raise ValueError("future mutation comparison shape mismatch")
    if not np.allclose(baseline_array, mutated_array, rtol=0.0, atol=absolute_tolerance):
        raise ValueError("FUTURE_MUTATION_INVARIANCE failed")

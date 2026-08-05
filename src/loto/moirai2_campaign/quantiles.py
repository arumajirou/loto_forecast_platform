from __future__ import annotations

from typing import Any, Iterable

import numpy as np

from loto.moirai2_campaign.model_manifest import NATIVE_QUANTILE_LEVELS


class QuantileValidationError(ValueError):
    pass


def quantile_key(level: float) -> str:
    return f"{level:.1f}"


def extract_native_quantiles(
    forecast: Any,
    *,
    horizon: int,
    position_count: int,
    levels: Iterable[float] = NATIVE_QUANTILE_LEVELS,
) -> dict[str, list[list[float]]]:
    expected = (horizon, position_count)
    normalized_levels = tuple(round(float(level), 10) for level in levels)
    if normalized_levels != NATIVE_QUANTILE_LEVELS:
        raise QuantileValidationError("quantile levels must exactly match native levels")
    arrays: list[np.ndarray] = []
    keys: list[str] = []
    for level in normalized_levels:
        array = np.asarray(forecast.quantile(float(level)), dtype=np.float64)
        if array.shape != expected:
            raise QuantileValidationError(
                f"quantile {level} shape mismatch: expected={expected}, actual={array.shape}"
            )
        if not np.isfinite(array).all():
            raise QuantileValidationError(f"quantile {level} contains NaN or Inf")
        keys.append(quantile_key(float(level)))
        arrays.append(array)
    stacked = np.stack(arrays, axis=0)
    if np.any(np.diff(stacked, axis=0) < 0):
        raise QuantileValidationError("native quantiles cross")
    return {key: array.tolist() for key, array in zip(keys, arrays, strict=True)}


def median_point_forecast(
    quantiles: dict[str, list[list[float]]],
) -> list[list[float]]:
    try:
        median = np.asarray(quantiles["0.5"], dtype=np.float64)
    except KeyError as exc:
        raise QuantileValidationError("native q0.5 is missing") from exc
    if median.ndim != 2 or not np.isfinite(median).all():
        raise QuantileValidationError("native q0.5 must be a finite horizon-by-position matrix")
    return median.tolist()

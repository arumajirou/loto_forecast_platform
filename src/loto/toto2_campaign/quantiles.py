from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from loto.toto2_campaign.model_manifest import NATIVE_QUANTILE_LEVELS


@dataclass(frozen=True)
class QuantileForecast:
    point_forecast: list[list[float]]
    quantiles: dict[str, list[list[float]]]
    native_shape: list[int]
    monotonic: bool


def quantile_key(level: float) -> str:
    return f"q{level:.1f}"


def extract_native_quantiles(
    values: np.ndarray,
    *,
    expected_series: int,
    expected_horizon: int,
) -> QuantileForecast:
    array = np.asarray(values)
    expected_shape = (
        len(NATIVE_QUANTILE_LEVELS),
        1,
        expected_series,
        expected_horizon,
    )
    if array.shape != expected_shape:
        raise ValueError(f"native output shape {array.shape} != {expected_shape}")
    if not np.issubdtype(array.dtype, np.number):
        raise ValueError("native output must be numeric")
    if not np.isfinite(array).all():
        raise ValueError("native output contains non-finite values")

    batch = array[:, 0, :, :].astype(float, copy=False)
    monotonic = bool(np.all(np.diff(batch, axis=0) >= 0.0))
    if not monotonic:
        raise ValueError("native quantiles cross")

    quantiles = {
        quantile_key(level): batch[index].tolist()
        for index, level in enumerate(NATIVE_QUANTILE_LEVELS)
    }
    point = quantiles["q0.5"]
    return QuantileForecast(
        point_forecast=point,
        quantiles=quantiles,
        native_shape=list(array.shape),
        monotonic=monotonic,
    )

from __future__ import annotations

import math
from collections.abc import Sequence

from loto.adapters.timer_s1.contracts import QUANTILE_KEYS

NormalizedMatrix = tuple[tuple[float, ...], ...]


def normalize_native_quantiles(
    native_output: Sequence[Sequence[Sequence[float]]],
    prediction_length: int,
) -> tuple[dict[str, NormalizedMatrix], NormalizedMatrix, tuple[int, int, int]]:
    series_count = len(native_output)
    if series_count == 0:
        raise ValueError("native output must contain at least one series")
    quantile_values: dict[str, list[tuple[float, ...]]] = {key: [] for key in QUANTILE_KEYS}
    for series_index, series in enumerate(native_output):
        if len(series) != 9:
            raise ValueError(f"series {series_index} must contain exactly nine quantiles")
        converted: list[tuple[float, ...]] = []
        for quantile_index, horizon in enumerate(series):
            values = tuple(float(value) for value in horizon)
            if len(values) != prediction_length:
                raise ValueError(
                    f"series {series_index} quantile {quantile_index} horizon mismatch"
                )
            if any(not math.isfinite(value) for value in values):
                raise ValueError("native output contains non-finite values")
            converted.append(values)
        for step in range(prediction_length):
            ordered = [converted[index][step] for index in range(9)]
            if any(left > right for left, right in zip(ordered, ordered[1:], strict=False)):
                raise ValueError("native quantiles cross")
        for key, values in zip(QUANTILE_KEYS, converted, strict=True):
            quantile_values[key].append(values)
    quantiles = {key: tuple(rows) for key, rows in quantile_values.items()}
    point = quantiles["q0.5"]
    return quantiles, point, (series_count, 9, prediction_length)

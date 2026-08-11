"""Trend and distribution-shift diagnostics for chronological development data."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy import stats

from loto.analysis.contracts import ChangePointResult, TrendResult


def _series(values: Sequence[float], *, min_n: int = 3) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError("values must be one-dimensional")
    if array.size < min_n:
        raise ValueError(f"values must contain at least {min_n} observations")
    if not np.isfinite(array).all():
        raise ValueError("values must contain only finite observations")
    return array


def linear_trend(values: Sequence[float]) -> TrendResult:
    """Fit a linear trend against the chronological observation index."""
    array = _series(values)
    if float(np.ptp(array)) == 0.0:
        raise ValueError("values must not be constant")
    time_index = np.arange(array.size, dtype=float)
    result = stats.linregress(time_index, array)
    return TrendResult(
        slope=float(result.slope),
        intercept=float(result.intercept),
        r_value=float(result.rvalue),
        p_value=float(result.pvalue),
        stderr=float(result.stderr),
        n=int(array.size),
    )


def _scan_absolute_mean_shift(array: np.ndarray, min_segment: int) -> tuple[int, float]:
    best_index = min_segment
    best_statistic = -1.0
    for split_index in range(min_segment, int(array.size) - min_segment + 1):
        left_mean = float(array[:split_index].mean())
        right_mean = float(array[split_index:].mean())
        statistic = abs(right_mean - left_mean)
        if statistic > best_statistic:
            best_index = split_index
            best_statistic = statistic
    return best_index, best_statistic


def _standardized_effect(left: np.ndarray, right: np.ndarray) -> float | None:
    left_variance = float(np.var(left, ddof=1))
    right_variance = float(np.var(right, ddof=1))
    degrees = left.size + right.size - 2
    if degrees <= 0:
        return None
    pooled_variance = (
        (left.size - 1) * left_variance + (right.size - 1) * right_variance
    ) / degrees
    if pooled_variance <= 0.0:
        return None
    return float((right.mean() - left.mean()) / math.sqrt(pooled_variance))


def mean_shift_scan(
    values: Sequence[float],
    *,
    min_segment: int = 10,
    repetitions: int = 2000,
    seed: int = 1,
) -> ChangePointResult:
    """Scan for the largest pre/post mean shift and calibrate it by permutation.

    Each permutation repeats the *entire* split scan, so the reported p-value accounts for
    selecting the largest candidate split within this one series. Correction across multiple
    series/features still belongs in ``loto.analysis.multiple_testing``.
    """
    if isinstance(min_segment, bool) or not isinstance(min_segment, int) or min_segment < 2:
        raise ValueError("min_segment must be an integer >= 2")
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")

    array = _series(values, min_n=2 * min_segment)
    split_index, observed_statistic = _scan_absolute_mean_shift(array, min_segment)
    left = array[:split_index]
    right = array[split_index:]
    left_mean = float(left.mean())
    right_mean = float(right.mean())
    mean_shift = right_mean - left_mean

    rng = np.random.default_rng(seed)
    exceedances = 0
    for _ in range(repetitions):
        permuted = rng.permutation(array)
        _, statistic = _scan_absolute_mean_shift(permuted, min_segment)
        if statistic >= observed_statistic - 1e-15:
            exceedances += 1
    p_value = (exceedances + 1.0) / (repetitions + 1.0)

    return ChangePointResult(
        split_index=split_index,
        left_mean=left_mean,
        right_mean=right_mean,
        mean_shift=float(mean_shift),
        absolute_mean_shift=float(observed_statistic),
        standardized_effect=_standardized_effect(left, right),
        permutation_p_value=float(p_value),
        repetitions=repetitions,
        seed=seed,
        min_segment=min_segment,
        n=int(array.size),
    )

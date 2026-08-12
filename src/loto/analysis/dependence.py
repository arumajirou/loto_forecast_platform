"""Association and serial-dependence tests for development data.

Association is representation-dependent. In particular, sorted lottery positions are constrained
by order statistics and can be correlated even under an IID draw mechanism. Results from this
module therefore always fail closed for causal interpretation.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy import stats

from loto.analysis.contracts import AssociationResult, RepresentationKind, SerialDependenceResult


def _series(values: Sequence[float], *, name: str, min_n: int = 3) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if array.size < min_n:
        raise ValueError(f"{name} must contain at least {min_n} observations")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")
    return array


def _nonconstant(array: np.ndarray, *, name: str) -> None:
    if float(np.ptp(array)) == 0.0:
        raise ValueError(f"{name} must not be constant")


def _correlation_bound(value: float) -> float:
    """Clamp harmless floating-point overshoot at the mathematical [-1, 1] boundary."""
    return max(-1.0, min(1.0, value))


def pearson_association(
    x: Sequence[float],
    y: Sequence[float],
    *,
    representation: RepresentationKind = "generic_numeric_series",
) -> AssociationResult:
    """Pearson product-moment association with a two-sided zero-correlation test."""
    left = _series(x, name="x")
    right = _series(y, name="y")
    if left.size != right.size:
        raise ValueError("x and y must have equal length")
    _nonconstant(left, name="x")
    _nonconstant(right, name="y")
    result = stats.pearsonr(left, right)
    statistic = _correlation_bound(float(result.statistic))
    p_value = float(result.pvalue)
    if not math.isfinite(statistic) or not math.isfinite(p_value):
        raise ValueError("Pearson result must be finite")
    return AssociationResult(
        method="pearson",
        statistic=statistic,
        p_value=p_value,
        n=int(left.size),
        representation=representation,
    )


def spearman_association(
    x: Sequence[float],
    y: Sequence[float],
    *,
    representation: RepresentationKind = "generic_numeric_series",
) -> AssociationResult:
    """Spearman rank association with a two-sided zero-association test."""
    left = _series(x, name="x")
    right = _series(y, name="y")
    if left.size != right.size:
        raise ValueError("x and y must have equal length")
    _nonconstant(left, name="x")
    _nonconstant(right, name="y")
    result = stats.spearmanr(left, right)
    statistic = _correlation_bound(float(result.statistic))
    p_value = float(result.pvalue)
    if not math.isfinite(statistic) or not math.isfinite(p_value):
        raise ValueError("Spearman result must be finite")
    return AssociationResult(
        method="spearman",
        statistic=statistic,
        p_value=p_value,
        n=int(left.size),
        representation=representation,
    )


def lag_autocorrelation(values: Sequence[float], lag: int) -> float:
    """Sample correlation between ``x[t]`` and ``x[t-lag]``."""
    array = _series(values, name="values", min_n=4)
    if isinstance(lag, bool) or not isinstance(lag, int) or lag < 1:
        raise ValueError("lag must be a positive integer")
    if lag >= array.size - 1:
        raise ValueError("lag must leave at least two paired observations")
    left = array[:-lag]
    right = array[lag:]
    _nonconstant(left, name="lagged left series")
    _nonconstant(right, name="lagged right series")
    correlation = _correlation_bound(float(np.corrcoef(left, right)[0, 1]))
    if not math.isfinite(correlation):
        raise ValueError("lag autocorrelation must be finite")
    return correlation


def ljung_box_test(values: Sequence[float], lags: int) -> SerialDependenceResult:
    """Ljung-Box portmanteau test through ``lags``.

    This is a serial-dependence diagnostic, not a causal test. The standard chi-square
    calibration is most appropriate for approximately stationary residual-like series.
    """
    array = _series(values, name="values", min_n=4)
    if isinstance(lags, bool) or not isinstance(lags, int) or lags < 1:
        raise ValueError("lags must be a positive integer")
    if lags >= array.size - 1:
        raise ValueError("lags must be smaller than n - 1")
    centered = array - float(array.mean())
    denominator = float(np.dot(centered, centered))
    if denominator <= 0.0:
        raise ValueError("values must not be constant")

    autocorrelations: list[float] = []
    for lag in range(1, lags + 1):
        numerator = float(np.dot(centered[lag:], centered[:-lag]))
        autocorrelations.append(_correlation_bound(numerator / denominator))

    n = int(array.size)
    q_statistic = (
        n
        * (n + 2.0)
        * sum(
            correlation**2 / (n - lag) for lag, correlation in enumerate(autocorrelations, start=1)
        )
    )
    p_value = float(stats.chi2.sf(q_statistic, df=lags))
    if not math.isfinite(q_statistic) or not math.isfinite(p_value):
        raise ValueError("Ljung-Box result must be finite")
    return SerialDependenceResult(
        lags=lags,
        statistic=float(q_statistic),
        p_value=p_value,
        autocorrelations=tuple(float(value) for value in autocorrelations),
        n=n,
    )

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np


def bias_offset(residuals: Sequence[float], statistic: str) -> float:
    values = np.asarray(residuals, dtype=float)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("bias residuals must be a non-empty finite vector")
    if statistic == "mean":
        return float(values.mean())
    if statistic == "median":
        return float(np.median(values))
    raise ValueError(f"unsupported bias statistic: {statistic}")


def quantile_residual_correction(
    residuals: Sequence[float],
    level: float,
    method: str,
) -> float:
    values = np.asarray(residuals, dtype=float)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("quantile residuals must be a non-empty finite vector")
    return float(np.quantile(values, level, method=method))


def finite_sample_conformal_quantile(
    scores: Sequence[float],
    *,
    coverage: float,
) -> float:
    values = np.asarray(scores, dtype=float)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("conformal scores must be a non-empty finite vector")
    if np.any(values < 0.0):
        raise ValueError("conformal scores must be non-negative")
    alpha = 1.0 - coverage
    rank = math.ceil((len(values) + 1) * (1.0 - alpha))
    probability = min(rank / len(values), 1.0)
    return float(np.quantile(values, probability, method="higher"))


def rearrange_quantiles(
    values: Mapping[float, float],
) -> tuple[dict[float, float], int]:
    levels = sorted(values)
    original = np.asarray([values[level] for level in levels], dtype=float)
    if not np.isfinite(original).all():
        raise ValueError("quantile values must be finite")
    rearranged = np.maximum.accumulate(original)
    changed = int(np.count_nonzero(~np.isclose(original, rearranged, rtol=0.0, atol=0.0)))
    return (
        {level: float(rearranged[index]) for index, level in enumerate(levels)},
        changed,
    )

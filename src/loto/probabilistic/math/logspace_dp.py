from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def as_log_weight_array(log_weights: Iterable[float] | FloatArray) -> FloatArray:
    """Return validated one-dimensional log weights.

    ``-inf`` is accepted and represents a zero weight. NaN and ``+inf`` are
    rejected because they make normalization ambiguous.
    """

    values = np.asarray(log_weights, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("log_weights must be one-dimensional")
    if values.size == 0:
        raise ValueError("log_weights must not be empty")
    if np.isnan(values).any() or np.isposinf(values).any():
        raise ValueError("log_weights must not contain NaN or +inf")
    return values


def validate_cardinality(n_items: int, cardinality: int) -> None:
    """Validate a fixed-cardinality subset request."""

    if not isinstance(cardinality, int):
        raise TypeError("cardinality must be an integer")
    if cardinality < 0 or cardinality > n_items:
        raise ValueError(f"cardinality must be in [0, {n_items}]")


def logsumexp_terms(terms: Iterable[float]) -> float:
    """Compute log-sum-exp without materializing exponentials."""

    result = float("-inf")
    for term in terms:
        result = float(np.logaddexp(result, float(term)))
    return result

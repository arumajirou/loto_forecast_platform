from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np
from numpy.typing import NDArray

from loto.probabilistic.math.elementary_symmetric import (
    conditional_bernoulli_log_probability,
)
from loto.probabilistic.math.logspace_dp import as_log_weight_array, validate_cardinality
from loto.probabilistic.math.psd import require_psd

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class ExhaustiveSubsetDistribution:
    subsets: tuple[tuple[int, ...], ...]
    log_probabilities: FloatArray
    probabilities: FloatArray


def enumerate_conditional_bernoulli(
    log_weights: FloatArray,
    cardinality: int,
) -> ExhaustiveSubsetDistribution:
    """Enumerate an exact toy conditional Bernoulli distribution."""

    values = as_log_weight_array(log_weights)
    validate_cardinality(values.size, cardinality)
    subsets = tuple(combinations(range(values.size), cardinality))
    log_probabilities = np.asarray(
        [conditional_bernoulli_log_probability(values, subset, cardinality) for subset in subsets],
        dtype=np.float64,
    )
    probabilities = np.exp(log_probabilities)
    return ExhaustiveSubsetDistribution(subsets, log_probabilities, probabilities)


def enumerate_kdpp(
    kernel: FloatArray,
    cardinality: int,
    *,
    tolerance: float = 1e-10,
) -> ExhaustiveSubsetDistribution:
    """Enumerate a k-DPP distribution for small verification fixtures."""

    evidence = require_psd(kernel, tolerance=tolerance, repair=False)
    n_items = evidence.matrix.shape[0]
    validate_cardinality(n_items, cardinality)
    subsets = tuple(combinations(range(n_items), cardinality))
    log_weights: list[float] = []
    for subset in subsets:
        if cardinality == 0:
            log_weights.append(0.0)
            continue
        principal = evidence.matrix[np.ix_(subset, subset)]
        sign, logdet = np.linalg.slogdet(principal)
        log_weights.append(float(logdet) if sign > 0 else float("-inf"))
    raw = np.asarray(log_weights, dtype=np.float64)
    finite = np.isfinite(raw)
    if not finite.any():
        raise ValueError("k-DPP normalizer is zero for the requested cardinality")
    log_normalizer = float(np.logaddexp.reduce(raw[finite]))
    log_probabilities = raw - log_normalizer
    probabilities = np.exp(log_probabilities)
    return ExhaustiveSubsetDistribution(subsets, log_probabilities, probabilities)

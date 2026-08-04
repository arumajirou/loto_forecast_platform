from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from numpy.typing import NDArray

from loto.probabilistic.math.logspace_dp import (
    as_log_weight_array,
    logsumexp_terms,
    validate_cardinality,
)

FloatArray = NDArray[np.float64]


def log_elementary_symmetric_table(
    log_weights: Iterable[float] | FloatArray,
    cardinality: int,
) -> FloatArray:
    """Build a stable prefix DP table for elementary symmetric polynomials.

    ``table[i, j]`` is the log of the degree-``j`` elementary symmetric
    polynomial over the first ``i`` weights.
    """

    values = as_log_weight_array(log_weights)
    validate_cardinality(values.size, cardinality)
    table = np.full((values.size + 1, cardinality + 1), -np.inf, dtype=np.float64)
    table[:, 0] = 0.0
    for i, log_weight in enumerate(values, start=1):
        upper = min(i, cardinality)
        for j in range(1, upper + 1):
            table[i, j] = np.logaddexp(
                table[i - 1, j],
                table[i - 1, j - 1] + log_weight,
            )
    return table


def log_elementary_symmetric(
    log_weights: Iterable[float] | FloatArray,
    cardinality: int,
) -> float:
    """Return ``log(e_k(exp(log_weights)))`` using log-space dynamic programming."""

    values = as_log_weight_array(log_weights)
    table = log_elementary_symmetric_table(values, cardinality)
    result = float(table[values.size, cardinality])
    if not np.isfinite(result) and cardinality > 0:
        raise ValueError("normalizer is zero for the requested cardinality")
    return result


def _suffix_table(log_weights: FloatArray, cardinality: int) -> FloatArray:
    n_items = log_weights.size
    table = np.full((n_items + 1, cardinality + 1), -np.inf, dtype=np.float64)
    table[:, 0] = 0.0
    for i in range(n_items - 1, -1, -1):
        upper = min(n_items - i, cardinality)
        for j in range(1, upper + 1):
            table[i, j] = np.logaddexp(
                table[i + 1, j],
                table[i + 1, j - 1] + log_weights[i],
            )
    return table


def fixed_cardinality_marginals(
    log_weights: Iterable[float] | FloatArray,
    cardinality: int,
) -> FloatArray:
    """Return exact inclusion probabilities for a conditional Bernoulli law."""

    values = as_log_weight_array(log_weights)
    validate_cardinality(values.size, cardinality)
    if cardinality == 0:
        return np.zeros(values.size, dtype=np.float64)
    if cardinality == values.size:
        return np.ones(values.size, dtype=np.float64)

    prefix = log_elementary_symmetric_table(values, cardinality)
    suffix = _suffix_table(values, cardinality)
    log_normalizer = float(prefix[values.size, cardinality])
    if not np.isfinite(log_normalizer):
        raise ValueError("normalizer is zero for the requested cardinality")

    marginals = np.zeros(values.size, dtype=np.float64)
    for index, log_weight in enumerate(values):
        exclusion_degree = cardinality - 1
        lower = max(0, exclusion_degree - (values.size - index - 1))
        upper = min(index, exclusion_degree)
        log_excluding = logsumexp_terms(
            prefix[index, left_degree] + suffix[index + 1, exclusion_degree - left_degree]
            for left_degree in range(lower, upper + 1)
        )
        log_marginal = log_weight + log_excluding - log_normalizer
        marginals[index] = 0.0 if np.isneginf(log_marginal) else float(np.exp(log_marginal))

    marginals = np.clip(marginals, 0.0, 1.0)
    if not np.isclose(marginals.sum(), cardinality, atol=1e-9, rtol=1e-9):
        raise RuntimeError("fixed-cardinality marginals failed the sum-to-k invariant")
    return marginals


def conditional_bernoulli_log_probability(
    log_weights: Iterable[float] | FloatArray,
    subset: Iterable[int],
    cardinality: int,
) -> float:
    """Return the normalized log probability of a fixed-cardinality subset."""

    values = as_log_weight_array(log_weights)
    validate_cardinality(values.size, cardinality)
    chosen = tuple(int(index) for index in subset)
    if len(chosen) != cardinality or len(set(chosen)) != cardinality:
        return float("-inf")
    if any(index < 0 or index >= values.size for index in chosen):
        return float("-inf")
    return float(values[list(chosen)].sum() - log_elementary_symmetric(values, cardinality))


def sample_conditional_bernoulli(
    log_weights: Iterable[float] | FloatArray,
    cardinality: int,
    *,
    rng: np.random.Generator,
) -> tuple[int, ...]:
    """Draw an exact fixed-cardinality conditional Bernoulli sample.

    The backward recursion uses the same prefix DP table as the normalizer and
    therefore never substitutes a Plackett-Luce/Gumbel-top-k approximation.
    """

    values = as_log_weight_array(log_weights)
    validate_cardinality(values.size, cardinality)
    if cardinality == 0:
        return ()
    if cardinality == values.size:
        return tuple(range(values.size))

    table = log_elementary_symmetric_table(values, cardinality)
    if not np.isfinite(table[values.size, cardinality]):
        raise ValueError("normalizer is zero for the requested cardinality")

    remaining = cardinality
    selected: list[int] = []
    for i in range(values.size, 0, -1):
        if remaining == 0:
            break
        if remaining == i:
            selected.extend(range(i))
            remaining = 0
            break
        log_include = values[i - 1] + table[i - 1, remaining - 1] - table[i, remaining]
        include_probability = 0.0 if np.isneginf(log_include) else float(np.exp(log_include))
        include_probability = float(np.clip(include_probability, 0.0, 1.0))
        if rng.random() < include_probability:
            selected.append(i - 1)
            remaining -= 1

    if remaining != 0:
        raise RuntimeError("conditional Bernoulli sampler failed to select k items")
    result = tuple(sorted(selected))
    if len(result) != cardinality or len(set(result)) != cardinality:
        raise RuntimeError("conditional Bernoulli sampler violated cardinality or uniqueness")
    return result

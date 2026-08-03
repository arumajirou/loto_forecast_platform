from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from loto.probabilistic.math.elementary_symmetric import (
    log_elementary_symmetric,
    sample_conditional_bernoulli,
)
from loto.probabilistic.math.logspace_dp import validate_cardinality
from loto.probabilistic.math.psd import PSDValidation, require_psd

FloatArray = NDArray[np.float64]
FloatMatrix = NDArray[np.float64]


@dataclass(frozen=True)
class PreparedKDPP:
    kernel: FloatMatrix
    cardinality: int
    eigenvalues: FloatArray
    eigenvectors: FloatMatrix
    log_normalizer: float
    psd_evidence: PSDValidation


def prepare_kdpp(
    kernel: ArrayLike,
    cardinality: int,
    *,
    tolerance: float = 1e-10,
    repair_psd: bool = False,
) -> PreparedKDPP:
    """Validate a k-DPP L-ensemble and compute its log normalizer."""

    evidence = require_psd(kernel, tolerance=tolerance, repair=repair_psd)
    validate_cardinality(evidence.matrix.shape[0], cardinality)
    eigenvalues, eigenvectors = np.linalg.eigh(evidence.matrix)
    eigenvalues = np.clip(eigenvalues, 0.0, None)
    log_eigenvalues = np.full(eigenvalues.shape, -np.inf, dtype=np.float64)
    positive = eigenvalues > 0.0
    log_eigenvalues[positive] = np.log(eigenvalues[positive])
    log_normalizer = log_elementary_symmetric(log_eigenvalues, cardinality)
    return PreparedKDPP(
        kernel=evidence.matrix,
        cardinality=cardinality,
        eigenvalues=eigenvalues,
        eigenvectors=eigenvectors,
        log_normalizer=log_normalizer,
        psd_evidence=evidence,
    )


def kdpp_subset_log_probability(
    prepared: PreparedKDPP,
    subset: tuple[int, ...] | list[int],
) -> float:
    """Return the normalized k-DPP log probability of one subset."""

    chosen = tuple(int(index) for index in subset)
    if len(chosen) != prepared.cardinality or len(set(chosen)) != prepared.cardinality:
        return float("-inf")
    if any(index < 0 or index >= prepared.kernel.shape[0] for index in chosen):
        return float("-inf")
    if prepared.cardinality == 0:
        return 0.0
    principal = prepared.kernel[np.ix_(chosen, chosen)]
    sign, logdet = np.linalg.slogdet(principal)
    if sign <= 0 or not np.isfinite(logdet):
        return float("-inf")
    return float(logdet - prepared.log_normalizer)


def _sample_projection_dpp(
    eigenvectors: FloatMatrix,
    *,
    rng: np.random.Generator,
    tolerance: float,
) -> tuple[int, ...]:
    vectors = np.asarray(eigenvectors, dtype=np.float64)
    selected: list[int] = []
    while vectors.shape[1] > 0:
        dimension = vectors.shape[1]
        probabilities = np.sum(vectors * vectors, axis=1) / dimension
        if selected:
            probabilities[np.asarray(selected, dtype=int)] = 0.0
        total = float(probabilities.sum())
        if not np.isfinite(total) or total <= tolerance:
            raise RuntimeError("k-DPP projection sampler lost probability mass")
        probabilities /= total
        item = int(rng.choice(vectors.shape[0], p=probabilities))
        selected.append(item)
        if dimension == 1:
            break

        column_weights = vectors[item, :] ** 2
        column_total = float(column_weights.sum())
        if column_total <= tolerance:
            raise RuntimeError("k-DPP projection sampler selected a zero row")
        column_weights /= column_total
        pivot_index = int(rng.choice(dimension, p=column_weights))
        pivot = vectors[:, pivot_index].copy()
        denominator = float(pivot[item])
        if abs(denominator) <= tolerance:
            raise RuntimeError("k-DPP projection sampler encountered an unstable pivot")

        remaining = np.delete(vectors, pivot_index, axis=1)
        remaining -= np.outer(pivot, remaining[item, :] / denominator)
        vectors, _ = np.linalg.qr(remaining, mode="reduced")
        vectors = vectors[:, : dimension - 1]

    result = tuple(sorted(selected))
    if len(result) != eigenvectors.shape[1] or len(set(result)) != len(result):
        raise RuntimeError("k-DPP sampler violated cardinality or uniqueness")
    return result


def sample_kdpp(
    prepared: PreparedKDPP,
    *,
    rng: np.random.Generator,
    tolerance: float = 1e-12,
) -> tuple[int, ...]:
    """Draw an exact k-DPP sample through eigenvector and projection sampling."""

    if prepared.cardinality == 0:
        return ()
    log_eigenvalues = np.full(prepared.eigenvalues.shape, -np.inf, dtype=np.float64)
    positive = prepared.eigenvalues > 0.0
    log_eigenvalues[positive] = np.log(prepared.eigenvalues[positive])
    selected_eigenvectors = sample_conditional_bernoulli(
        log_eigenvalues,
        prepared.cardinality,
        rng=rng,
    )
    projection_basis = prepared.eigenvectors[:, list(selected_eigenvectors)]
    return _sample_projection_dpp(projection_basis, rng=rng, tolerance=tolerance)

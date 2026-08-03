from __future__ import annotations

from itertools import combinations

import numpy as np
import pytest

from loto.probabilistic.math import (
    conditional_bernoulli_log_probability,
    enumerate_conditional_bernoulli,
    enumerate_kdpp,
    fixed_cardinality_marginals,
    kdpp_subset_log_probability,
    log_elementary_symmetric,
    prepare_kdpp,
    sample_conditional_bernoulli,
    sample_kdpp,
    validate_psd,
)


def test_elementary_symmetric_matches_enumeration_for_k_up_to_ten() -> None:
    rng = np.random.default_rng(20260803)
    for n_items in range(1, 11):
        logits = rng.normal(0.0, 2.0, size=n_items)
        for cardinality in range(n_items + 1):
            expected_terms = [
                float(logits[list(subset)].sum())
                for subset in combinations(range(n_items), cardinality)
            ]
            expected = float(np.logaddexp.reduce(np.asarray(expected_terms)))
            observed = log_elementary_symmetric(logits, cardinality)
            assert observed == pytest.approx(expected, abs=1e-10)


def test_conditional_bernoulli_probability_sum_and_dp_logp() -> None:
    logits = np.asarray([-2.0, -0.25, 0.5, 1.25, 3.0])
    distribution = enumerate_conditional_bernoulli(logits, 3)
    assert distribution.probabilities.sum() == pytest.approx(1.0, abs=1e-12)
    for subset, log_probability in zip(
        distribution.subsets,
        distribution.log_probabilities,
        strict=True,
    ):
        assert conditional_bernoulli_log_probability(logits, subset, 3) == pytest.approx(
            log_probability,
            abs=1e-12,
        )


def test_extreme_logits_remain_finite_and_normalized() -> None:
    logits = np.asarray([-1000.0, -500.0, 0.0, 500.0, 1000.0])
    log_normalizer = log_elementary_symmetric(logits, 2)
    marginals = fixed_cardinality_marginals(logits, 2)
    distribution = enumerate_conditional_bernoulli(logits, 2)
    assert np.isfinite(log_normalizer)
    assert np.isfinite(marginals).all()
    assert marginals.sum() == pytest.approx(2.0, abs=1e-9)
    assert distribution.probabilities.sum() == pytest.approx(1.0, abs=1e-12)
    assert not np.isnan(distribution.probabilities).any()


def test_marginals_equal_finite_difference_gradient() -> None:
    logits = np.asarray([-1.5, -0.2, 0.4, 1.7, 2.1])
    cardinality = 2
    analytic = fixed_cardinality_marginals(logits, cardinality)
    epsilon = 1e-6
    finite_difference = np.zeros_like(logits)
    for index in range(logits.size):
        plus = logits.copy()
        minus = logits.copy()
        plus[index] += epsilon
        minus[index] -= epsilon
        finite_difference[index] = (
            log_elementary_symmetric(plus, cardinality)
            - log_elementary_symmetric(minus, cardinality)
        ) / (2.0 * epsilon)
    assert np.isfinite(finite_difference).all()
    assert analytic == pytest.approx(finite_difference, abs=2e-7)


def test_conditional_bernoulli_sampler_is_exact_cardinality_and_deterministic() -> None:
    logits = np.asarray([-3.0, -1.0, 0.0, 0.5, 2.0, 4.0])
    first_rng = np.random.default_rng(91)
    second_rng = np.random.default_rng(91)
    first = [sample_conditional_bernoulli(logits, 3, rng=first_rng) for _ in range(100)]
    second = [sample_conditional_bernoulli(logits, 3, rng=second_rng) for _ in range(100)]
    assert first == second
    assert all(len(sample) == 3 and len(set(sample)) == 3 for sample in first)


def test_equal_weights_are_uniform_over_fixed_cardinality_subsets() -> None:
    distribution = enumerate_conditional_bernoulli(np.zeros(6), 3)
    expected = 1.0 / len(distribution.subsets)
    assert distribution.probabilities == pytest.approx(expected, abs=1e-12)


def test_psd_validation_is_fail_closed_and_repair_is_explicit() -> None:
    indefinite = np.asarray([[1.0, 2.0], [2.0, 1.0]])
    rejected = validate_psd(indefinite, repair=False)
    repaired = validate_psd(indefinite, repair=True)
    assert rejected.is_psd is False
    assert rejected.repaired is False
    assert repaired.is_psd is True
    assert repaired.repaired is True
    assert repaired.jitter_added > 0.0
    assert repaired.min_eigenvalue_after >= -repaired.tolerance


def test_kdpp_normalization_and_subset_log_probability() -> None:
    coordinates = np.arange(5, dtype=np.float64)[:, None]
    distance_squared = (coordinates - coordinates.T) ** 2
    similarity = np.exp(-distance_squared / 2.0)
    quality = np.asarray([0.7, 1.0, 1.4, 0.8, 1.2])
    kernel = np.diag(quality) @ similarity @ np.diag(quality)
    prepared = prepare_kdpp(kernel, 2)
    exhaustive = enumerate_kdpp(kernel, 2)
    assert exhaustive.probabilities.sum() == pytest.approx(1.0, abs=1e-12)
    for subset, log_probability in zip(
        exhaustive.subsets,
        exhaustive.log_probabilities,
        strict=True,
    ):
        assert kdpp_subset_log_probability(prepared, subset) == pytest.approx(
            log_probability,
            abs=1e-10,
        )


def test_diagonal_kdpp_matches_conditional_bernoulli() -> None:
    diagonal = np.asarray([0.2, 0.5, 1.0, 2.0, 5.0])
    kernel = np.diag(diagonal)
    kdpp = enumerate_kdpp(kernel, 3)
    bernoulli = enumerate_conditional_bernoulli(np.log(diagonal), 3)
    assert kdpp.subsets == bernoulli.subsets
    assert kdpp.probabilities == pytest.approx(bernoulli.probabilities, abs=1e-12)


def test_kdpp_sampler_cardinality_uniqueness_and_seed_determinism() -> None:
    coordinates = np.arange(7, dtype=np.float64)[:, None]
    similarity = np.exp(-((coordinates - coordinates.T) ** 2) / 3.0)
    prepared = prepare_kdpp(similarity, 3, repair_psd=True)
    first_rng = np.random.default_rng(412)
    second_rng = np.random.default_rng(412)
    first = [sample_kdpp(prepared, rng=first_rng) for _ in range(80)]
    second = [sample_kdpp(prepared, rng=second_rng) for _ in range(80)]
    assert first == second
    assert all(len(sample) == 3 and len(set(sample)) == 3 for sample in first)


def test_singular_kdpp_subset_is_negative_infinity() -> None:
    kernel = np.asarray(
        [
            [1.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    prepared = prepare_kdpp(kernel, 2)
    assert kdpp_subset_log_probability(prepared, (0, 1)) == float("-inf")

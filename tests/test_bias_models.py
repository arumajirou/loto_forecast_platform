from __future__ import annotations

import numpy as np
import pytest

from loto.game.geometry import geometry_for
from loto.models.bias import (
    fit_dirichlet_categorical_bias,
    fit_weighted_subset_bias,
    mix_positional_distributions,
)


def test_dirichlet_categorical_bias_is_smoothed_and_position_aware() -> None:
    geometry = geometry_for("numbers3")
    history = np.asarray([[1, 2, 3]] * 20 + [[9, 2, 3]] * 2, dtype=int)

    model = fit_dirichlet_categorical_bias(history, geometry, prior_strength=10.0)
    probabilities = model.predict_distribution(geometry)

    assert probabilities.shape == (geometry.positions, geometry.universe_size)
    assert np.allclose(probabilities.sum(axis=1), 1.0)
    assert np.all(probabilities > 0)
    assert probabilities[0, 1] > probabilities[0, 9]
    assert probabilities[1, 2] == pytest.approx(probabilities[2, 3])


def test_dirichlet_decay_weights_recent_history_more() -> None:
    geometry = geometry_for("numbers3")
    history = np.asarray([[1, 1, 1]] * 20 + [[8, 8, 8]] * 5, dtype=int)

    unweighted = fit_dirichlet_categorical_bias(history, geometry, prior_strength=1.0)
    decayed = fit_dirichlet_categorical_bias(
        history,
        geometry,
        prior_strength=1.0,
        decay=0.8,
    )

    assert decayed.predict_distribution(geometry)[0, 8] > unweighted.predict_distribution(geometry)[0, 8]


def test_weighted_subset_sampler_is_legal_fixed_cardinality_and_bias_sensitive() -> None:
    geometry = geometry_for("mini")
    rng = np.random.default_rng(3)
    universe = np.arange(geometry.value_min, geometry.value_max + 1)
    history = []
    for _ in range(80):
        pool = np.delete(universe, np.where(universe == 1))
        tail = rng.choice(pool, size=geometry.positions - 1, replace=False)
        history.append(sorted([1, *tail.tolist()]))
    model = fit_weighted_subset_bias(np.asarray(history, dtype=int), geometry, prior_strength=10.0)

    samples = model.sample(geometry, n_samples=2000, seed=11)

    assert samples.shape == (2000, geometry.positions)
    assert np.all(np.diff(samples, axis=1) > 0)
    assert np.all(samples >= geometry.value_min)
    assert np.all(samples <= geometry.value_max)
    inclusion_one = float(np.mean(np.any(samples == 1, axis=1)))
    null_rate = geometry.positions / geometry.universe_size
    assert inclusion_one > null_rate


def test_uniformish_weighted_subset_produces_normalized_positional_marginals() -> None:
    geometry = geometry_for("mini")
    rng = np.random.default_rng(9)
    universe = np.arange(geometry.value_min, geometry.value_max + 1)
    history = np.asarray(
        [sorted(rng.choice(universe, size=geometry.positions, replace=False).tolist()) for _ in range(1000)],
        dtype=int,
    )
    model = fit_weighted_subset_bias(history, geometry, prior_strength=100.0)

    marginals = model.positional_marginals(geometry, n_samples=3000, seed=5)

    assert marginals.shape == (geometry.positions, geometry.universe_size)
    assert np.allclose(marginals.sum(axis=1), 1.0)


def test_null_shrinkage_is_explicit_and_normalized() -> None:
    null = np.asarray([[0.5, 0.5], [0.5, 0.5]], dtype=float)
    bias = np.asarray([[0.9, 0.1], [0.2, 0.8]], dtype=float)

    assert np.allclose(mix_positional_distributions(null, bias, alpha=0.0), null)
    assert np.allclose(mix_positional_distributions(null, bias, alpha=1.0), bias)
    midpoint = mix_positional_distributions(null, bias, alpha=0.5)
    assert np.allclose(midpoint.sum(axis=1), 1.0)

    with pytest.raises(ValueError, match="alpha"):
        mix_positional_distributions(null, bias, alpha=1.1)

from __future__ import annotations

import importlib.util

import numpy as np
import pytest
from scipy.stats import norm

from loto.probabilistic.backends import get_backend
from loto.probabilistic.catalog import get_probabilistic_model_spec
from loto.probabilistic.contracts import ProbabilisticRunConfig, TargetMode
from loto.probabilistic.dataset import synthetic_dataset, task_arrays
from loto.probabilistic.models.copula_native import (
    MODEL_ID,
    GaussianCopulaCategoricalState,
    categories_from_latent,
    fit_gaussian_copula_categorical,
)


def _config(**updates: object) -> ProbabilisticRunConfig:
    payload: dict[str, object] = {
        "posterior_draws": 32,
        "native_draws": 8,
        "native_warmup": 8,
        "native_chains": 1,
        "native_inner_cores": 1,
        "native_progressbar": False,
        "native_max_train_rows": 80,
        "copula_marginal_prior": 0.5,
        "copula_lkj_eta": 2.0,
        "copula_scale_prior_sigma": 0.1,
        "copula_threshold_epsilon": 1e-6,
        "copula_correlation_shrinkage": 0.05,
        "copula_correlation_floor": 1e-8,
    }
    payload.update(updates)
    return ProbabilisticRunConfig.model_validate(payload)


def _latent_categorical(
    correlation: np.ndarray,
    *,
    rows: int,
    classes: int,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    latent = rng.multivariate_normal(
        np.zeros(correlation.shape[0]), correlation, size=rows, check_valid="raise"
    )
    cumulative = np.arange(1, classes) / classes
    thresholds = np.array(
        [[-np.inf, *norm.ppf(cumulative), np.inf] for _ in range(correlation.shape[0])]
    )
    return categories_from_latent(latent, thresholds)


def test_copula_independence_recovers_near_identity() -> None:
    observations = _latent_categorical(np.eye(3), rows=5000, classes=4, seed=4)
    state = fit_gaussian_copula_categorical(
        observations,
        game="numbers3",
        classes=4,
        config=_config(),
        seed=11,
    )
    off_diagonal = state.correlation - np.eye(3)
    assert np.max(np.abs(off_diagonal)) < 0.10
    assert np.linalg.eigvalsh(state.correlation).min() >= -1e-9


def test_copula_recovers_positive_and_negative_dependence_signs() -> None:
    expected = np.array(
        [
            [1.0, 0.65, -0.45],
            [0.65, 1.0, -0.25],
            [-0.45, -0.25, 1.0],
        ]
    )
    observations = _latent_categorical(expected, rows=6000, classes=5, seed=8)
    state = fit_gaussian_copula_categorical(
        observations,
        game="numbers3",
        classes=5,
        config=_config(),
        seed=12,
    )
    assert state.correlation[0, 1] > 0.35
    assert state.correlation[0, 2] < -0.20
    assert state.correlation[1, 2] < -0.08


def test_joint_sampling_preserves_margins_and_category_bounds() -> None:
    expected = np.array(
        [
            [1.0, 0.55, 0.20],
            [0.55, 1.0, 0.35],
            [0.20, 0.35, 1.0],
        ]
    )
    observations = _latent_categorical(expected, rows=4000, classes=4, seed=15)
    state = fit_gaussian_copula_categorical(
        observations,
        game="numbers3",
        classes=4,
        config=_config(),
        seed=16,
    )
    samples = state.joint_samples(draws=30000, seed=17)
    empirical = state.empirical_marginals(samples)
    assert samples.shape == (30000, 3)
    assert samples.min() >= 0
    assert samples.max() < 4
    assert np.max(np.abs(empirical - state.marginal_probabilities)) < 0.025


def test_correlation_is_psd_and_state_roundtrip_is_exact(tmp_path) -> None:
    nearly_singular = np.array(
        [
            [1.0, 0.95, 0.90, 0.85],
            [0.95, 1.0, 0.92, 0.88],
            [0.90, 0.92, 1.0, 0.94],
            [0.85, 0.88, 0.94, 1.0],
        ]
    )
    observations = _latent_categorical(nearly_singular, rows=5000, classes=3, seed=21)
    state = fit_gaussian_copula_categorical(
        observations,
        game="numbers4",
        classes=3,
        config=_config(copula_correlation_shrinkage=0.01),
        seed=22,
    )
    state.save(tmp_path)
    loaded = GaussianCopulaCategoricalState.load(tmp_path)
    assert np.array_equal(loaded.marginal_probabilities, state.marginal_probabilities)
    assert np.array_equal(loaded.thresholds, state.thresholds)
    assert np.array_equal(loaded.correlation, state.correlation)
    assert np.array_equal(
        loaded.joint_samples(draws=512, seed=99),
        state.joint_samples(draws=512, seed=99),
    )
    assert np.linalg.eigvalsh(loaded.correlation).min() >= -1e-9


def test_label_and_position_mapping_are_fixed() -> None:
    thresholds = np.array(
        [
            [-np.inf, -1.0, 0.0, 1.0, np.inf],
            [-np.inf, -0.5, 0.5, 1.5, np.inf],
        ]
    )
    latent = np.array(
        [
            [-2.0, -1.0],
            [-0.5, 0.0],
            [0.5, 1.0],
            [2.0, 2.0],
        ]
    )
    categories = categories_from_latent(latent, thresholds)
    assert categories.tolist() == [[0, 0], [1, 1], [2, 2], [3, 3]]

    observations = np.tile(categories, (100, 1))
    state = fit_gaussian_copula_categorical(
        observations,
        game="numbers3",
        classes=4,
        config=_config(),
        seed=31,
    )
    assert state.label_order == (tuple(range(4)), tuple(range(4)))
    assert state.positions == 2


def test_builtin_runtime_and_primary_pymc_contract() -> None:
    bundle = synthetic_dataset("numbers3", rows=100, seed=42)
    y, classes = task_arrays(bundle, TargetMode.JOINT_DISCRETE_COPULA)
    spec = get_probabilistic_model_spec(MODEL_ID)
    posterior = get_backend("builtin").execute(
        spec,
        y=y[:80],
        classes=classes,
        target_mode=TargetMode.JOINT_DISCRETE_COPULA,
        geometry=bundle.geometry,
        config=_config(posterior_draws=32),
        seed=43,
    )
    assert spec.primary_backend == "pymc"
    assert spec.primary_profile == "pymc-nuts"
    assert posterior.probability_draws.shape == (32, 3, 10)
    assert np.isfinite(posterior.probability_draws).all()
    assert np.allclose(posterior.probability_draws.sum(axis=-1), 1.0)
    assert posterior.diagnostics["correlation_psd"] is True
    assert posterior.metadata["implementation_kind"] == "analytic_copula_initialization"


@pytest.mark.skipif(
    importlib.util.find_spec("pymc") is None or importlib.util.find_spec("arviz") is None,
    reason="PyMC and ArviZ are required for the primary runtime smoke test",
)
def test_primary_pymc_runtime_when_environment_is_compatible() -> None:
    backend = get_backend("pymc")
    probe = backend.probe()
    if not probe.available:
        pytest.skip(f"PyMC runtime probe is blocked: {probe.detail}")

    bundle = synthetic_dataset("numbers3", rows=100, seed=51)
    y, classes = task_arrays(bundle, TargetMode.JOINT_DISCRETE_COPULA)
    spec = get_probabilistic_model_spec(MODEL_ID)
    posterior = backend.execute(
        spec,
        y=y[:50],
        classes=classes,
        target_mode=TargetMode.JOINT_DISCRETE_COPULA,
        geometry=bundle.geometry,
        config=_config(native_draws=8, native_warmup=8, native_max_train_rows=50),
        seed=52,
        inference_profile_id="pymc-nuts",
    )
    assert posterior.probability_draws.shape == (8, 3, 10)
    assert posterior.diagnostics["correlation_posterior_finite"] is True
    assert posterior.diagnostics["correlation_posterior_psd"] is True
    assert posterior.diagnostics["marginal_preservation"] is True

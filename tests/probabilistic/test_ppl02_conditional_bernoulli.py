from __future__ import annotations

from pathlib import Path

import numpy as np

from loto.probabilistic.backends import get_backend
from loto.probabilistic.catalog import get_probabilistic_model_spec
from loto.probabilistic.config import load_run_config, write_resolved_config
from loto.probabilistic.contracts import ProbabilisticRunConfig
from loto.probabilistic.dataset import synthetic_dataset, task_arrays
from loto.probabilistic.math.elementary_symmetric import sample_conditional_bernoulli
from loto.probabilistic.models.subset_native import (
    MODEL_ID,
    ConditionalBernoulliPosterior,
    fit_conditional_bernoulli_map,
    frequency_fixed_k_log_probability,
    uniform_fixed_k_log_probability,
)
from loto.probabilistic.planner import build_plan


def _config(**updates: object) -> ProbabilisticRunConfig:
    defaults: dict[str, object] = {
        "models": [MODEL_ID],
        "games": ["loto7"],
        "posterior_draws": 32,
        "native_draws": 32,
        "native_max_train_rows": 500,
        "test_size": 2,
        "min_train_size": 80,
        "subset_prior_scale": 4.0,
        "subset_max_iter": 1000,
        "subset_gradient_tolerance": 1e-3,
    }
    defaults.update(updates)
    return ProbabilisticRunConfig.model_validate(defaults)


def _simulate_indicator(
    logits: np.ndarray,
    cardinality: int,
    *,
    rows: int,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    indicator = np.zeros((rows, logits.size), dtype=int)
    for row in range(rows):
        selected = sample_conditional_bernoulli(logits, cardinality, rng=rng)
        indicator[row, list(selected)] = 1
    return indicator


def test_catalog_and_builtin_registration() -> None:
    spec = get_probabilistic_model_spec(MODEL_ID)
    assert spec.family == "fixed_subset"
    assert spec.tasks == ("fixed_cardinality_subset",)
    assert spec.primary_backend == "builtin"
    assert spec.native_graph_id == "conditional_bernoulli_fixed_k_v1"
    assert spec.backends == ("builtin",)


def test_config_round_trip_preserves_subset_parameters(tmp_path: Path) -> None:
    config = _config(
        subset_prior_scale=3.5,
        subset_initial_pseudocount=0.75,
        subset_laplace_ridge=1e-7,
        subset_research_gain_min=0.02,
        subset_ece_bins=12,
    )
    path = write_resolved_config(config, tmp_path / "resolved.yaml")
    loaded = load_run_config(path)
    assert loaded == config


def test_map_laplace_is_deterministic_and_legal() -> None:
    logits = np.linspace(-1.5, 1.5, 8)
    indicator = _simulate_indicator(logits, 3, rows=180, seed=7)
    config = _config(games=["loto7"], subset_prior_scale=5.0)
    first = fit_conditional_bernoulli_map(
        indicator,
        game="toy",
        config=config,
        seed=42,
        cardinality=3,
    )
    second = fit_conditional_bernoulli_map(
        indicator,
        game="toy",
        config=config,
        seed=42,
        cardinality=3,
    )
    assert np.allclose(first.map_logits, second.map_logits)
    assert np.allclose(first.logit_draws, second.logit_draws)
    assert np.array_equal(first.joint_samples, second.joint_samples)
    assert np.allclose(first.candidate_marginal_draws.sum(axis=1), 3.0)
    assert np.allclose(first.normalized_probability_draws.sum(axis=-1), 1.0)
    assert all(len(set(sample.tolist())) == 3 for sample in first.joint_samples)
    assert np.corrcoef(first.map_logits, logits)[0, 1] > 0.85


def test_posterior_save_load_round_trip(tmp_path: Path) -> None:
    logits = np.linspace(-0.8, 0.8, 7)
    indicator = _simulate_indicator(logits, 3, rows=120, seed=8)
    posterior = fit_conditional_bernoulli_map(
        indicator,
        game="toy",
        config=_config(),
        seed=9,
        cardinality=3,
    )
    posterior.save(tmp_path)
    loaded = ConditionalBernoulliPosterior.load(tmp_path)
    assert loaded.to_metadata_dict() == posterior.to_metadata_dict()
    assert np.allclose(loaded.map_logits, posterior.map_logits)
    assert np.allclose(loaded.covariance, posterior.covariance)
    assert np.allclose(loaded.candidate_marginal_draws, posterior.candidate_marginal_draws)
    assert np.array_equal(loaded.joint_samples, posterior.joint_samples)
    subset = tuple(int(index) for index in posterior.joint_samples[0])
    assert loaded.posterior_predictive_log_probability(subset) == (
        posterior.posterior_predictive_log_probability(subset)
    )


def test_cutoff_isolation_ignores_future_rows() -> None:
    logits = np.linspace(-1.0, 1.0, 8)
    indicator = _simulate_indicator(logits, 3, rows=140, seed=10)
    cutoff = 100
    altered = indicator.copy()
    altered[cutoff:] = np.roll(altered[cutoff:], shift=2, axis=1)
    config = _config()
    first = fit_conditional_bernoulli_map(
        indicator[:cutoff],
        game="toy",
        config=config,
        seed=11,
        cardinality=3,
    )
    second = fit_conditional_bernoulli_map(
        altered[:cutoff],
        game="toy",
        config=config,
        seed=11,
        cardinality=3,
    )
    assert np.array_equal(first.logit_draws, second.logit_draws)
    assert np.array_equal(first.joint_samples, second.joint_samples)


def test_baselines_are_finite_and_frequency_uses_training_only() -> None:
    indicator = _simulate_indicator(np.linspace(-0.5, 0.5, 7), 3, rows=100, seed=12)
    actual = tuple(np.flatnonzero(indicator[-1]).tolist())
    uniform = uniform_fixed_k_log_probability(7, 3)
    frequency = frequency_fixed_k_log_probability(indicator[:-1], actual, pseudocount=0.5)
    assert np.isfinite(uniform)
    assert np.isfinite(frequency)
    changed_future = indicator.copy()
    changed_future[-1] = np.roll(changed_future[-1], 1)
    assert frequency_fixed_k_log_probability(
        changed_future[:-1], actual, pseudocount=0.5
    ) == frequency


def test_builtin_backend_emits_joint_evidence(tmp_path: Path) -> None:
    bundle = synthetic_dataset("loto7", rows=90, seed=13)
    config = _config()
    plan = build_plan(config)
    assert len(plan) == 1
    trial = plan[0]
    assert trial.allowed
    y, classes = task_arrays(bundle, trial.target_mode)
    native = get_backend("builtin").execute(
        get_probabilistic_model_spec(MODEL_ID),
        y=y[:80],
        classes=classes,
        target_mode=trial.target_mode,
        geometry=bundle.geometry,
        config=config,
        seed=trial.seed,
    )
    assert isinstance(native.native_payload, ConditionalBernoulliPosterior)
    posterior = native.native_payload
    assert native.probability_draws.shape == (32, 1, bundle.geometry.universe_size)
    assert np.isfinite(native.probability_draws).all()
    assert np.allclose(native.probability_draws.sum(axis=-1), 1.0)
    assert np.allclose(posterior.candidate_marginal_draws.sum(axis=1), 7.0)
    assert all(len(set(sample.tolist())) == 7 for sample in posterior.joint_samples)

    posterior.save(tmp_path)
    loaded = ConditionalBernoulliPosterior.load(tmp_path)
    assert loaded.to_metadata_dict() == posterior.to_metadata_dict()
    assert np.array_equal(loaded.joint_samples, posterior.joint_samples)
    assert (tmp_path / "conditional_bernoulli_posterior.json").exists()
    assert (tmp_path / "conditional_bernoulli_posterior.npz").exists()

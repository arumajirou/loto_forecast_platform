from __future__ import annotations

import numpy as np
import pytest

from loto.probabilistic.backends import get_backend
from loto.probabilistic.catalog import get_probabilistic_model_spec
from loto.probabilistic.contracts import ProbabilisticRunConfig, TargetMode
from loto.probabilistic.dataset import synthetic_dataset, task_arrays
from loto.probabilistic.models.dglm_native import (
    MODEL_ID,
    MultinomialDGLMState,
    fit_multinomial_dglm,
)


def _config(**updates: object) -> ProbabilisticRunConfig:
    values: dict[str, object] = {
        "posterior_draws": 32,
        "native_draws": 32,
        "dglm_discount_factor": 0.97,
        "dglm_prior_variance": 1.0,
        "dglm_include_trend": False,
    }
    values.update(updates)
    return ProbabilisticRunConfig.model_validate(values)


def test_static_multinomial_state_is_finite_and_psd() -> None:
    rng = np.random.default_rng(10)
    probabilities = np.array([0.55, 0.30, 0.15])
    observations = rng.choice(3, size=(400, 2), p=probabilities)
    state = fit_multinomial_dglm(
        observations,
        game="synthetic",
        classes=3,
        config=_config(dglm_discount_factor=0.995),
        seed=42,
    )

    prediction = state.predictive_probabilities()
    assert prediction.shape == (2, 3)
    assert np.isfinite(prediction).all()
    assert np.allclose(prediction.sum(axis=1), 1.0)
    assert np.all(np.abs(prediction - probabilities) < 0.15)
    for covariance in state.state_covariance:
        assert np.allclose(covariance, covariance.T, atol=1e-10)
        assert np.linalg.eigvalsh(covariance).min() >= -1e-9


def test_dglm_tracks_abrupt_shift_and_gradual_drift() -> None:
    rng = np.random.default_rng(4)
    first = rng.choice(3, size=120, p=[0.80, 0.10, 0.10])
    transition = np.array(
        [rng.choice(3, p=[0.80 - 0.70 * i / 79, 0.10, 0.10 + 0.70 * i / 79]) for i in range(80)]
    )
    final = rng.choice(3, size=120, p=[0.10, 0.10, 0.80])
    observations = np.concatenate([first, transition, final])[:, None]
    state = fit_multinomial_dglm(
        observations,
        game="synthetic",
        classes=3,
        config=_config(dglm_discount_factor=0.94),
        seed=42,
    )

    history = state.one_step_probabilities[:, 0]
    assert history[-1, 2] > history[120, 2]
    assert history[-1, 2] > history[-1, 0]
    assert state.predictive_probabilities()[0, 2] > 0.55


def test_predict_before_update_prevents_same_row_leakage() -> None:
    rng = np.random.default_rng(6)
    observations = rng.integers(0, 4, size=(80, 1)).astype(float)
    changed = observations.copy()
    changed[35, 0] = (changed[35, 0] + 1) % 4

    original_state = fit_multinomial_dglm(
        observations,
        game="synthetic",
        classes=4,
        config=_config(),
        seed=12,
    )
    changed_state = fit_multinomial_dglm(
        changed,
        game="synthetic",
        classes=4,
        config=_config(),
        seed=12,
    )

    assert np.array_equal(
        original_state.one_step_probabilities[:36],
        changed_state.one_step_probabilities[:36],
    )
    assert not np.array_equal(
        original_state.one_step_probabilities[36],
        changed_state.one_step_probabilities[36],
    )


def test_missing_draw_is_skipped_without_state_corruption() -> None:
    observations = np.array([[0.0], [1.0], [np.nan], [2.0], [1.0]])
    state = fit_multinomial_dglm(
        observations,
        game="synthetic",
        classes=3,
        config=_config(),
        seed=42,
    )

    assert state.update_applied[:, 0].tolist() == [True, True, False, True, True]
    assert np.isfinite(state.state_mean).all()
    assert np.isfinite(state.state_covariance).all()
    assert np.isfinite(state.predictive_probabilities()).all()


def test_saved_state_resume_matches_continuous_run(tmp_path) -> None:
    rng = np.random.default_rng(17)
    observations = rng.integers(0, 3, size=(140, 2))
    exogenous = np.column_stack([np.sin(np.arange(140) / 7.0), np.cos(np.arange(140) / 11.0)])
    config = _config(dglm_seasonal_periods=[12.0])

    continuous = fit_multinomial_dglm(
        observations,
        game="synthetic",
        classes=3,
        config=config,
        seed=99,
        exogenous=exogenous,
    )
    first = fit_multinomial_dglm(
        observations[:70],
        game="synthetic",
        classes=3,
        config=config,
        seed=99,
        exogenous=exogenous[:70],
    )
    paths = first.save(tmp_path)
    assert {path.name for path in paths} == {
        "multinomial_dglm_state.json",
        "multinomial_dglm_state.npz",
    }
    loaded = MultinomialDGLMState.load(tmp_path)
    resumed = fit_multinomial_dglm(
        observations[70:],
        game="synthetic",
        classes=3,
        config=config,
        seed=99,
        exogenous=exogenous[70:],
        initial_state=loaded,
    )

    assert resumed.current_step == continuous.current_step
    assert resumed.state_names == continuous.state_names
    assert np.array_equal(resumed.state_mean, continuous.state_mean)
    assert np.array_equal(resumed.state_covariance, continuous.state_covariance)
    assert np.array_equal(resumed.one_step_probabilities, continuous.one_step_probabilities)
    next_exogenous = np.array([0.2, -0.1])
    assert np.array_equal(
        resumed.probability_draws(draws=16, seed=123, exogenous=next_exogenous),
        continuous.probability_draws(draws=16, seed=123, exogenous=next_exogenous),
    )


def test_catalog_backend_and_config_contracts() -> None:
    spec = get_probabilistic_model_spec(MODEL_ID)
    assert spec.tasks == (TargetMode.DYNAMIC_MULTINOMIAL,)
    assert spec.primary_backend == "builtin"
    assert spec.dynamic is True
    assert spec.supports_exogenous is True

    config = _config(dglm_seasonal_periods=[12.0, 52.0])
    restored = ProbabilisticRunConfig.model_validate(config.model_dump(mode="json"))
    assert restored == config
    with pytest.raises(ValueError, match="greater than one"):
        _config(dglm_seasonal_periods=[1.0])
    with pytest.raises(ValueError, match="duplicates"):
        _config(dglm_seasonal_periods=[12.0, 12.0])

    bundle = synthetic_dataset("numbers3", rows=90, seed=5)
    y, classes = task_arrays(bundle, TargetMode.DYNAMIC_MULTINOMIAL)
    posterior = get_backend("builtin").execute(
        spec,
        y=y[:80],
        classes=classes,
        target_mode=TargetMode.DYNAMIC_MULTINOMIAL,
        geometry=bundle.geometry,
        config=config,
        seed=42,
    )
    assert posterior.probability_draws.shape == (32, 3, 10)
    assert np.isfinite(posterior.probability_draws).all()
    assert np.allclose(posterior.probability_draws.sum(axis=-1), 1.0)
    assert posterior.diagnostics["state_covariance_psd"] is True

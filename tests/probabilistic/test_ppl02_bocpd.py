from __future__ import annotations

import numpy as np
import pytest

from loto.game.geometry import geometry_for
from loto.probabilistic.backends import get_backend
from loto.probabilistic.catalog import get_probabilistic_model_spec
from loto.probabilistic.compatibility import decide_compatibility
from loto.probabilistic.contracts import ProbabilisticRunConfig, TargetMode
from loto.probabilistic.dataset import synthetic_dataset, task_arrays
from loto.probabilistic.models.bocpd_native import (
    MODEL_ID,
    RETRAIN_EVENT,
    BOCPDDirichletCategoricalState,
    fit_bocpd_dirichlet_categorical,
)


def _config(**updates: object) -> ProbabilisticRunConfig:
    values: dict[str, object] = {
        "posterior_draws": 32,
        "native_draws": 32,
        "bocpd_hazard_type": "constant",
        "bocpd_expected_run_length": 100.0,
        "bocpd_max_run_length": 256,
        "bocpd_posterior_mass_prune": 1e-10,
        "bocpd_prior_concentration": 0.5,
        "bocpd_alert_threshold": 0.5,
        "bocpd_min_evidence_count": 20,
        "bocpd_cooldown": 10,
        "bocpd_min_observed_fraction": 1.0,
    }
    values.update(updates)
    return ProbabilisticRunConfig.model_validate(values)


def test_no_change_has_controlled_false_alert_rate() -> None:
    rng = np.random.default_rng(3)
    observations = np.column_stack(
        [rng.choice(4, size=300, p=[0.75, 0.10, 0.10, 0.05]) for _ in range(3)]
    )
    state = fit_bocpd_dirichlet_categorical(
        observations,
        game="synthetic",
        classes=4,
        config=_config(),
        seed=11,
    )
    assert len(state.alert_events) == 0
    assert float((state.changepoint_probabilities >= 0.5).mean()) <= 0.01
    assert np.isclose(state.run_length_posterior.sum(), 1.0)


def test_known_change_raises_posterior_and_retrain_event() -> None:
    observations = np.vstack(
        [
            np.zeros((100, 3), dtype=np.int64),
            np.full((100, 3), 3, dtype=np.int64),
        ]
    )
    state = fit_bocpd_dirichlet_categorical(
        observations,
        game="numbers3",
        classes=4,
        config=_config(),
        seed=12,
    )
    assert state.one_step_probabilities[100, :, 0].min() > 0.95
    assert state.changepoint_probabilities[100] > 0.90
    assert [event["step"] for event in state.alert_events] == [100]
    assert state.alert_events[0]["event_type"] == RETRAIN_EVENT
    assert state.alert_events[0]["automatic_retraining"] is False


def test_repeated_changes_are_detected_with_cooldown() -> None:
    observations = np.vstack(
        [
            np.zeros((60, 3), dtype=np.int64),
            np.full((60, 3), 2, dtype=np.int64),
            np.full((60, 3), 1, dtype=np.int64),
        ]
    )
    state = fit_bocpd_dirichlet_categorical(
        observations,
        game="numbers3",
        classes=4,
        config=_config(bocpd_cooldown=20),
        seed=13,
    )
    assert state.changepoint_probabilities[60] > 0.90
    assert state.changepoint_probabilities[120] > 0.90
    assert [event["step"] for event in state.alert_events] == [60, 120]


def test_single_outlier_does_not_create_permanent_change() -> None:
    observations = np.vstack(
        [
            np.zeros((100, 3), dtype=np.int64),
            np.full((1, 3), 3, dtype=np.int64),
            np.zeros((80, 3), dtype=np.int64),
        ]
    )
    state = fit_bocpd_dirichlet_categorical(
        observations,
        game="numbers3",
        classes=4,
        config=_config(),
        seed=14,
    )
    assert state.changepoint_probabilities[100] > 0.90
    assert state.changepoint_probabilities[102:].max() < 0.01
    assert state.predictive_probabilities()[:, 0].min() > 0.95
    assert len(state.alert_events) == 1


def test_mass_pruning_records_discarded_mass_and_hard_run_length_cap() -> None:
    observations = np.zeros((100, 2), dtype=np.int64)
    state = fit_bocpd_dirichlet_categorical(
        observations,
        game="synthetic",
        classes=4,
        config=_config(
            bocpd_expected_run_length=30.0,
            bocpd_max_run_length=8,
            bocpd_posterior_mass_prune=1e-4,
            bocpd_alert_threshold=0.99,
        ),
        seed=15,
    )
    assert state.run_lengths.max() <= 8
    assert state.pruned_mass_history.max() > 0.0
    assert np.all((state.pruned_mass_history >= 0.0) & (state.pruned_mass_history <= 1.0))
    assert np.isclose(state.run_length_posterior.sum(), 1.0)


def test_resume_and_state_roundtrip_match_continuous_execution(tmp_path) -> None:
    observations = np.vstack(
        [
            np.zeros((80, 3), dtype=np.int64),
            np.full((80, 3), 2, dtype=np.int64),
        ]
    )
    config = _config()
    full = fit_bocpd_dirichlet_categorical(
        observations,
        game="numbers3",
        classes=4,
        config=config,
        seed=16,
    )
    first = fit_bocpd_dirichlet_categorical(
        observations[:90],
        game="numbers3",
        classes=4,
        config=config,
        seed=16,
    )
    first.save(tmp_path)
    restored = BOCPDDirichletCategoricalState.load(tmp_path)
    resumed = fit_bocpd_dirichlet_categorical(
        observations[90:],
        game="numbers3",
        classes=4,
        config=config,
        seed=16,
        initial_state=restored,
    )
    assert np.array_equal(resumed.run_lengths, full.run_lengths)
    assert np.allclose(resumed.run_length_posterior, full.run_length_posterior)
    assert np.allclose(resumed.dirichlet_alpha, full.dirichlet_alpha)
    assert np.allclose(resumed.one_step_probabilities, full.one_step_probabilities)
    assert np.allclose(resumed.changepoint_probabilities, full.changepoint_probabilities)
    assert resumed.alert_events == full.alert_events
    assert np.array_equal(
        resumed.probability_draws(32, seed=99),
        full.probability_draws(32, seed=99),
    )


def test_predict_before_update_and_data_quality_gate() -> None:
    prefix = np.zeros((40, 2), dtype=np.float64)
    first = np.vstack([prefix, np.array([[1.0, 1.0]])])
    second = np.vstack([prefix, np.array([[3.0, 3.0]])])
    config = _config(bocpd_min_evidence_count=1)
    first_state = fit_bocpd_dirichlet_categorical(
        first,
        game="synthetic",
        classes=4,
        config=config,
        seed=17,
    )
    second_state = fit_bocpd_dirichlet_categorical(
        second,
        game="synthetic",
        classes=4,
        config=config,
        seed=17,
    )
    assert np.array_equal(
        first_state.one_step_probabilities[40],
        second_state.one_step_probabilities[40],
    )

    missing = np.vstack([prefix, np.array([[np.nan, np.nan]])])
    missing_state = fit_bocpd_dirichlet_categorical(
        missing,
        game="synthetic",
        classes=4,
        config=_config(
            bocpd_alert_threshold=0.0,
            bocpd_min_evidence_count=1,
            bocpd_min_observed_fraction=1.0,
        ),
        seed=18,
    )
    assert missing_state.data_quality_pass[-1] is np.False_
    assert all(event["step"] != 40 for event in missing_state.alert_events)


@pytest.mark.parametrize("game", ["mini", "loto6", "loto7", "numbers3", "numbers4"])
def test_catalog_compatibility_for_all_games(game: str) -> None:
    spec = get_probabilistic_model_spec(MODEL_ID)
    decision = decide_compatibility(
        spec,
        geometry=geometry_for(game),
        backend="builtin",
        include_experimental=True,
    )
    assert decision.allowed
    assert decision.details[0] == "target_mode=online_changepoint"


def test_builtin_runtime_contract_is_finite_and_auditable() -> None:
    bundle = synthetic_dataset("numbers3", rows=100, seed=21)
    y, classes = task_arrays(bundle, TargetMode.ONLINE_CHANGEPOINT)
    spec = get_probabilistic_model_spec(MODEL_ID)
    posterior = get_backend("builtin").execute(
        spec,
        y=y[:80],
        classes=classes,
        target_mode=TargetMode.ONLINE_CHANGEPOINT,
        geometry=bundle.geometry,
        config=_config(posterior_draws=32),
        seed=22,
    )
    assert spec.primary_backend == "builtin"
    assert spec.primary_profile is None
    assert posterior.probability_draws.shape == (32, 3, 10)
    assert np.isfinite(posterior.probability_draws).all()
    assert np.allclose(posterior.probability_draws.sum(axis=-1), 1.0)
    assert posterior.diagnostics["run_length_posterior_valid"] is True
    assert posterior.metadata["implementation_kind"] == "exact_online_message_passing"
    assert posterior.metadata["automatic_retraining"] is False

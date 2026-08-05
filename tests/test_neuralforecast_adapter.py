import pytest

from loto.models.neuralforecast_adapter import (
    AutoModelRequest,
    choose_backend,
    resolve_auto_model_plan,
)
from loto.models.neuralforecast_search_space import SearchSpaceCompleteness


def test_backend_policy_uses_optuna_by_default_and_ray_for_cpu_parallelism():
    assert choose_backend(gpus=1, cpus=16, requested=None) == "optuna"
    assert choose_backend(gpus=0, cpus=16, requested=None, parallel_trials=8) == "ray"


def test_tsmixer_requires_n_series():
    with pytest.raises(ValueError):
        resolve_auto_model_plan(AutoModelRequest(model_name="AutoTSMixer", h=1, config={}))


def test_timesnet_fft_forces_full_precision():
    plan = resolve_auto_model_plan(
        AutoModelRequest(model_name="AutoTimesNet", h=1, precision="16-mixed", config={})
    )
    assert plan.precision == "32-true"
    assert "precision_adjusted_for_fft" in plan.adjustments


def test_early_stop_is_placed_inside_model_config_not_constructor_kwargs():
    plan = resolve_auto_model_plan(
        AutoModelRequest(model_name="AutoNHITS", h=1, early_stop_patience_steps=5, config={})
    )
    assert plan.config["early_stop_patience_steps"] == 5
    assert "early_stop_patience_steps" not in plan.constructor_kwargs


def test_plan_resolution_is_dependency_light_and_uses_shared_policy():
    plan = resolve_auto_model_plan(
        AutoModelRequest(
            model_name="AutoNHITS",
            h=1,
            backend="ray",
            num_samples=10,
            random_seed=1,
        )
    )

    assert plan.search_algorithm == "OptunaSearch"
    assert plan.search_policy is not None
    assert plan.search_policy.model_name == "AutoNHITS"
    assert plan.search_policy.search_seed == 1
    assert "search_alg" not in plan.constructor_kwargs


def test_default_plan_marks_runtime_search_space_unavailable():
    plan = resolve_auto_model_plan(
        AutoModelRequest(model_name="AutoNHITS", h=1, backend="optuna")
    )

    assert plan.search_space_profile is not None
    assert plan.search_space_profile.completeness is SearchSpaceCompleteness.UNAVAILABLE
    assert "delegated" in plan.search_space_profile.probe_errors[0]


def test_explicit_config_is_profiled_as_fixed():
    plan = resolve_auto_model_plan(
        AutoModelRequest(
            model_name="AutoNHITS",
            h=1,
            backend="optuna",
            config={"learning_rate": 1e-3, "max_steps": 100},
        )
    )

    assert plan.search_space_profile is not None
    assert plan.search_space_profile.completeness is SearchSpaceCompleteness.COMPLETE
    assert plan.search_space_profile.tunable_count == 0
    assert plan.search_space_profile.constant_count == 2

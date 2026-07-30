import pytest

from loto.models.neuralforecast_adapter import AutoModelRequest, choose_backend, resolve_auto_model_plan


def test_backend_policy_uses_optuna_by_default_and_ray_for_cpu_parallelism():
    assert choose_backend(gpus=1, cpus=16, requested=None) == "optuna"
    assert choose_backend(gpus=0, cpus=16, requested=None, parallel_trials=8) == "ray"


def test_tsmixer_requires_n_series():
    with pytest.raises(ValueError):
        resolve_auto_model_plan(AutoModelRequest(model_name="AutoTSMixer", h=1, config={}))


def test_timesnet_fft_forces_full_precision():
    plan = resolve_auto_model_plan(AutoModelRequest(model_name="AutoTimesNet", h=1, precision="16-mixed", config={}))
    assert plan.precision == "32-true"
    assert "precision_adjusted_for_fft" in plan.adjustments


def test_early_stop_is_placed_inside_model_config_not_constructor_kwargs():
    plan = resolve_auto_model_plan(AutoModelRequest(model_name="AutoNHITS", h=1, early_stop_patience_steps=5, config={}))
    assert plan.config["early_stop_patience_steps"] == 5
    assert "early_stop_patience_steps" not in plan.constructor_kwargs

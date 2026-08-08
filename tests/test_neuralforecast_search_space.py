import hashlib
from loto.models.neuralforecast_search_space import (
    SearchSpaceCompleteness,
    profile_fixed_config,
    profile_optuna_config,
    profile_ray_config,
    unavailable_search_space_profile,
    write_search_space_profile,
)


class Integer:
    def __init__(self, low, high):
        self.lower, self.upper = low, high


class Categorical:
    def __init__(self, values):
        self.categories = values


def test_ray_profile_is_complete():
    profile = profile_ray_config({"x": Integer(1, 5), "mode": Categorical(["a", "b"])})
    assert profile.completeness is SearchSpaceCompleteness.COMPLETE
    assert profile.tunable_count == 2
    assert profile.finite_combination_count == 8
    assert profile.grid_eligible is True
    assert profile.cmaes_eligible is False


def test_optuna_profile_is_partial_and_detects_branch():
    def config(trial):
        family = trial.suggest_categorical("family", ["a", "b"])
        result = {"family": family, "rate": trial.suggest_float("rate", 1e-4, 1e-2, log=True)}
        if family == "b":
            result["width"] = trial.suggest_int("width", 16, 64, step=16)
        return result

    profile = profile_optuna_config(config)
    assert profile.completeness is SearchSpaceCompleteness.PARTIAL
    assert profile.conditional is True
    assert profile.cmaes_eligible is False


def test_fixed_and_unavailable_states_are_explicit(tmp_path):
    fixed = profile_fixed_config({"max_steps": 100}, backend="optuna")
    assert fixed.constant_count == 1 and fixed.tunable_count == 0
    unavailable = unavailable_search_space_profile(
        backend="optuna", model_name="AutoNHITS", reason="delegated"
    )
    assert unavailable.completeness is SearchSpaceCompleteness.UNAVAILABLE
    artifact = write_search_space_profile(tmp_path, fixed)
    expected = hashlib.sha256((tmp_path / "SEARCH_SPACE_PROFILE.json").read_bytes()).hexdigest()
    assert artifact["sha256"] == expected

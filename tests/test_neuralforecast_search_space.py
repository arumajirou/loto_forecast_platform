import hashlib
import json

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


def test_ray_profile_serializes_callable_categories_without_mutating_cardinality():
    profile = profile_ray_config(
        {
            "activation": Categorical([len, "ReLU"]),
            "nested": [len, {"fn": max}],
        },
        model_name="AutoDLinear",
    )

    payload = profile.model_dump(mode="json")
    raw = json.dumps(payload, sort_keys=True)

    activation = next(item for item in payload["dimensions"] if item["name"] == "activation")
    nested = next(item for item in payload["dimensions"] if item["name"] == "nested")

    assert activation["cardinality"] == 2
    assert activation["choices"][0] == {"type": "callable", "path": "builtins.len"}
    assert nested["value"][0] == {"type": "callable", "path": "builtins.len"}
    assert nested["value"][1]["fn"] == {"type": "callable", "path": "builtins.max"}
    assert "builtin_function_or_method" not in raw


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


def test_optuna_profile_records_callable_choice_json_safely_but_returns_raw_choice():
    seen = []

    def config(trial):
        value = trial.suggest_categorical("callable", [len])
        seen.append(value)
        return {"callable": value}

    profile = profile_optuna_config(config)
    payload = profile.model_dump(mode="json")
    dimension = next(item for item in payload["dimensions"] if item["name"] == "callable")

    assert seen == [len, len, len]
    assert dimension["choices"] == [{"type": "callable", "path": "builtins.len"}]
    json.dumps(payload)


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

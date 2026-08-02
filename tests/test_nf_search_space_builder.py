from __future__ import annotations

import json
from pathlib import Path

from ray.tune.search.sample import (
    Categorical,
    Float,
    Integer,
)

from loto.nf_search_space_builder import (
    build_optuna_config,
    build_ray_space,
)

SOURCE = Path("configs/generated/neuralforecast_normalized_fixed_seed_spaces.json")


class RecordingTrial:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def suggest_categorical(
        self,
        name,
        choices,
    ):
        self.calls.append(("categorical", name, choices))
        return choices[0]

    def suggest_float(
        self,
        name,
        low,
        high,
        *,
        step=None,
        log=False,
    ):
        self.calls.append(
            (
                "float",
                name,
                low,
                high,
                step,
                log,
            )
        )
        return low

    def suggest_int(
        self,
        name,
        low,
        high,
        *,
        step=1,
        log=False,
    ):
        self.calls.append(
            (
                "int",
                name,
                low,
                high,
                step,
                log,
            )
        )
        return low


def load_spaces():
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def test_every_model_builds_optuna_config():
    data = load_spaces()

    for _model, spec in data["models"].items():
        trial = RecordingTrial()

        config = build_optuna_config(
            trial,
            spec["parameters"],
        )

        assert config
        assert config["random_seed"] == 42

        if "step_size" in config:
            assert config["step_size"] == 1


def test_every_model_builds_ray_space():
    data = load_spaces()

    for _model, spec in data["models"].items():
        space = build_ray_space(spec["parameters"])

        assert space
        assert space["random_seed"] == 42

        if "step_size" in space:
            assert space["step_size"] == 1


def test_ray_domain_types_are_created():
    parameters = {
        "category": {
            "kind": "categorical",
            "values": [1, 2],
        },
        "uniform": {
            "kind": "float",
            "lower": 0.0,
            "upper": 1.0,
            "step": None,
            "log": False,
        },
        "loguniform": {
            "kind": "log_float",
            "lower": 0.0001,
            "upper": 0.1,
            "step": None,
            "log": True,
        },
        "integer": {
            "kind": "integer",
            "lower": 1,
            "upper": 3,
            "step": 1,
            "log": False,
        },
    }

    space = build_ray_space(parameters)

    assert isinstance(
        space["category"],
        Categorical,
    )
    assert isinstance(
        space["uniform"],
        Float,
    )
    assert isinstance(
        space["loguniform"],
        Float,
    )
    assert isinstance(
        space["integer"],
        Integer,
    )

    assert space["integer"].lower == 1
    assert space["integer"].upper == 4

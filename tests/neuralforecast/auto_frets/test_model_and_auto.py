from __future__ import annotations

from types import SimpleNamespace

import pytest
import torch
from torch import nn
from torch.nn import functional

from loto.neuralforecast.auto_frets.auto import build_auto_frets_class
from loto.neuralforecast.auto_frets.contracts import expected_parameter_count
from loto.neuralforecast.auto_frets.model import build_frets_class


class PointLoss:
    outputsize_multiplier = 1


class DistributionLoss:
    outputsize_multiplier = 2


class Losses:
    @staticmethod
    def MAE() -> PointLoss:
        return PointLoss()


class FakeBaseModel(nn.Module):
    def __init__(self, **kwargs):
        super().__init__()
        self.__dict__.update(kwargs)
        self.h = kwargs["h"]
        self.input_size = kwargs["input_size"]


class FakeBaseAuto:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    @classmethod
    def _ray_config_to_optuna(cls, config):
        return ("optuna", config)


class BasicVariantGenerator:
    def __init__(self, random_state: int):
        self.random_state = random_state


class RandomSampler:
    def __init__(self, seed: int):
        self.seed = seed


class Domain:
    def __init__(self, kind: str, value):
        self.kind = kind
        self.value = value


class Tune:
    @staticmethod
    def choice(value):
        return Domain("choice", value)

    @staticmethod
    def loguniform(low, high):
        return Domain("loguniform", (low, high))

    @staticmethod
    def randint(low, high):
        return Domain("randint", (low, high))


def _frets_class():
    return build_frets_class(
        base_model=FakeBaseModel,
        functional=functional,
        losses=Losses,
        nn=nn,
        torch=torch,
        module_name="test_auto_frets_runtime",
    )


def test_frets_forward_shape_finite_and_state_roundtrip() -> None:
    model_class = _frets_class()
    model = model_class(
        h=2,
        architecture_profile="compact",
        training_profile="smoke",
    )
    observed = sum(parameter.numel() for parameter in model.parameters())
    assert observed == expected_parameter_count(model.input_size, model.h)
    values = torch.linspace(0.0, 1.0, steps=3 * model.input_size).reshape(
        3,
        model.input_size,
        1,
    )
    prediction = model({"insample_y": values})
    assert tuple(prediction.shape) == (3, 2, 1)
    assert torch.isfinite(prediction).all().item()

    clone = model_class(
        h=2,
        architecture_profile="compact",
        training_profile="smoke",
    )
    clone.load_state_dict(model.state_dict(), strict=True)
    replay = clone({"insample_y": values})
    assert torch.equal(prediction, replay)


def test_frets_rejects_distribution_loss_and_non_float32() -> None:
    model_class = _frets_class()
    with pytest.raises(ValueError, match="point training losses"):
        model_class(
            h=1,
            architecture_profile="compact",
            training_profile="smoke",
            loss=DistributionLoss(),
        )
    model = model_class(
        h=1,
        architecture_profile="compact",
        training_profile="smoke",
    )
    values = torch.ones(2, model.input_size, 1, dtype=torch.float64)
    with pytest.raises(ValueError, match="float32"):
        model({"insample_y": values})


def test_auto_frets_builds_ray_and_optuna_configs() -> None:
    auto_class = build_auto_frets_class(
        base_auto=FakeBaseAuto,
        basic_variant_generator=BasicVariantGenerator,
        frets_class=_frets_class(),
        losses=Losses,
        random_sampler=RandomSampler,
        tune=Tune,
        module_name="test_auto_frets_runtime",
    )
    ray_config = auto_class.get_default_config(h=1, backend="ray")
    assert ray_config["precision"] == "32-true"
    assert ray_config["architecture_profile"].value == [
        "compact",
        "balanced",
        "wide",
    ]
    optuna_config = auto_class.get_default_config(h=1, backend="optuna")
    assert optuna_config[0] == "optuna"

    ray_model = auto_class(h=1, backend="ray")
    assert ray_model.kwargs["search_alg"].random_state == 1
    assert ray_model.loto_model_id == "nf-local-auto-frets"
    optuna_model = auto_class(h=1, backend="optuna")
    assert optuna_model.kwargs["search_alg"].seed == 1


def test_auto_frets_rejects_unknown_backend() -> None:
    auto_class = build_auto_frets_class(
        base_auto=FakeBaseAuto,
        basic_variant_generator=BasicVariantGenerator,
        frets_class=_frets_class(),
        losses=Losses,
        random_sampler=RandomSampler,
        tune=Tune,
        module_name="test_auto_frets_runtime",
    )
    with pytest.raises(ValueError, match="unsupported"):
        auto_class.get_default_config(h=1, backend="unknown")

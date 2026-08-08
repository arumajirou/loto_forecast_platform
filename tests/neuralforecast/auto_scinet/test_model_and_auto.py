from __future__ import annotations

from typing import Any

import pytest
import torch
import torch.nn as nn
import torch.nn.functional as functional

from loto.neuralforecast.auto_scinet.auto import build_auto_scinet_class
from loto.neuralforecast.auto_scinet.model import build_scinet_class


class PointLoss:
    outputsize_multiplier = 1


class DistributionLoss:
    outputsize_multiplier = 3


class Losses:
    @staticmethod
    def MAE() -> PointLoss:
        return PointLoss()


class FakeBaseModel(nn.Module):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__()
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.h = kwargs["h"]
        self.input_size = kwargs["input_size"]


class FakeBaseAuto:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    @classmethod
    def _ray_config_to_optuna(cls, config: dict[str, Any]):
        def define(_trial: Any) -> dict[str, Any]:
            return dict(config)

        return define


class FakeSearch:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class Tune:
    @staticmethod
    def choice(values: list[Any]) -> tuple[str, tuple[Any, ...]]:
        return ("choice", tuple(values))

    @staticmethod
    def loguniform(low: float, high: float) -> tuple[str, float, float]:
        return ("loguniform", low, high)

    @staticmethod
    def randint(low: int, high: int) -> tuple[str, int, int]:
        return ("randint", low, high)


def _model_class() -> type[Any]:
    return build_scinet_class(
        base_model=FakeBaseModel,
        functional=functional,
        losses=Losses,
        nn=nn,
        torch=torch,
        module_name="test_auto_scinet",
    )


def test_real_torch_forward_and_structure() -> None:
    model_class = _model_class()
    torch.manual_seed(1)
    model = model_class(
        h=2,
        architecture_profile="compact",
        training_profile="smoke",
    )
    values = torch.linspace(0.0, 1.0, steps=3 * model.input_size).reshape(
        3,
        model.input_size,
        1,
    )
    output = model({"insample_y": values})
    assert output.shape == (3, 2, 1)
    assert torch.isfinite(output).all().item()
    names = [type(module).__name__ for module in model.modules()]
    assert names.count("SCIBlock") == 15
    assert names.count("CausalConvBlock") == 60
    assert sum(parameter.numel() for parameter in model.parameters()) == 1008


def test_state_dict_roundtrip_is_exact() -> None:
    model_class = _model_class()
    torch.manual_seed(1)
    first = model_class(
        h=1,
        architecture_profile="compact",
        training_profile="smoke",
    )
    values = torch.randn(2, first.input_size, 1)
    expected = first({"insample_y": values})
    second = model_class(
        h=1,
        architecture_profile="compact",
        training_profile="smoke",
    )
    second.load_state_dict(first.state_dict(), strict=True)
    actual = second({"insample_y": values})
    assert torch.equal(expected, actual)


def test_nonfinite_and_distribution_loss_are_rejected() -> None:
    model_class = _model_class()
    with pytest.raises(ValueError, match="point training"):
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
    values = torch.ones(1, model.input_size, 1)
    values[0, 0, 0] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        model({"insample_y": values})


def test_auto_factory_supports_ray_and_optuna() -> None:
    model_class = _model_class()
    auto_class = build_auto_scinet_class(
        base_auto=FakeBaseAuto,
        basic_variant_generator=FakeSearch,
        random_sampler=FakeSearch,
        losses=Losses,
        scinet_class=model_class,
        tune=Tune,
        module_name="test_auto_scinet",
    )
    ray = auto_class(h=1, backend="ray")
    optuna = auto_class(h=1, backend="optuna")
    assert ray.kwargs["cls_model"] is model_class
    assert ray.kwargs["backend"] == "ray"
    assert optuna.kwargs["backend"] == "optuna"
    assert callable(optuna.kwargs["config"])
    assert ray.loto_model_id == "nf-local-auto-scinet"


def test_auto_search_space_has_no_architecture_drift_knobs() -> None:
    model_class = _model_class()
    auto_class = build_auto_scinet_class(
        base_auto=FakeBaseAuto,
        basic_variant_generator=FakeSearch,
        random_sampler=FakeSearch,
        losses=Losses,
        scinet_class=model_class,
        tune=Tune,
        module_name="test_auto_scinet",
    )
    config = auto_class.get_default_config(h=1, backend="ray")
    assert set(config) == {
        "h",
        "architecture_profile",
        "training_profile",
        "learning_rate",
        "batch_size",
        "windows_batch_size",
        "scaler_type",
        "random_seed",
    }

from __future__ import annotations

import sys
import types
from dataclasses import dataclass

import pytest
import torch
import torch.nn as nn

from loto.neuralforecast.auto_segrnn import runtime


class _PointLoss:
    outputsize_multiplier = 1


class _DistributionLoss:
    outputsize_multiplier = 2


class _FakeBaseModel(nn.Module):
    def __init__(self, **kwargs):
        super().__init__()
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.h = kwargs["h"]
        self.input_size = kwargs["input_size"]
        self.loss = kwargs["loss"]


class _FakeBaseAuto:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    @staticmethod
    def _ray_config_to_optuna(config):
        def config_fn(trial):
            del trial
            return {key: getattr(value, "default", value) for key, value in config.items()}

        return config_fn


@dataclass
class _Domain:
    default: object


class _Tune:
    @staticmethod
    def choice(values):
        return _Domain(values[0])

    @staticmethod
    def loguniform(low, high):
        del high
        return _Domain(low)

    @staticmethod
    def randint(low, high):
        del high
        return _Domain(low)


class _BasicVariantGenerator:
    def __init__(self, random_state):
        self.random_state = random_state


class _RandomSampler:
    def __init__(self, seed):
        self.seed = seed


def _install_runtime_doubles(monkeypatch) -> None:
    neuralforecast = types.ModuleType("neuralforecast")
    common = types.ModuleType("neuralforecast.common")
    base_auto = types.ModuleType("neuralforecast.common._base_auto")
    base_model = types.ModuleType("neuralforecast.common._base_model")
    losses_package = types.ModuleType("neuralforecast.losses")
    losses = types.ModuleType("neuralforecast.losses.pytorch")
    ray = types.ModuleType("ray")
    ray_tune = types.ModuleType("ray.tune")
    ray_search = types.ModuleType("ray.tune.search")
    ray_basic = types.ModuleType("ray.tune.search.basic_variant")
    optuna = types.ModuleType("optuna")
    samplers = types.ModuleType("optuna.samplers")

    base_auto.BaseAuto = _FakeBaseAuto
    base_model.BaseModel = _FakeBaseModel
    losses.MAE = _PointLoss
    losses_package.pytorch = losses
    ray.tune = _Tune
    ray_tune.search = ray_search
    ray_basic.BasicVariantGenerator = _BasicVariantGenerator
    samplers.RandomSampler = _RandomSampler
    optuna.samplers = samplers

    modules = {
        "neuralforecast": neuralforecast,
        "neuralforecast.common": common,
        "neuralforecast.common._base_auto": base_auto,
        "neuralforecast.common._base_model": base_model,
        "neuralforecast.losses": losses_package,
        "neuralforecast.losses.pytorch": losses,
        "ray": ray,
        "ray.tune": ray_tune,
        "ray.tune.search": ray_search,
        "ray.tune.search.basic_variant": ray_basic,
        "optuna": optuna,
        "optuna.samplers": samplers,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    monkeypatch.setattr(
        runtime,
        "runtime_dependency_status",
        lambda: {
            "neuralforecast": True,
            "optuna": True,
            "ray": True,
            "torch": True,
        },
    )
    runtime._reset_runtime_classes_for_tests()


def test_dependency_light_package_import() -> None:
    status = runtime.runtime_dependency_status()
    assert set(status) == {"neuralforecast", "optuna", "ray", "torch"}


def test_segrnn_forward_shape_and_finite(monkeypatch) -> None:
    _install_runtime_doubles(monkeypatch)
    model_class = runtime.get_segrnn_class()
    model = model_class(
        h=5,
        architecture_profile="balanced",
        training_profile="smoke",
        loss=_PointLoss(),
        dropout=0.0,
    )
    x = torch.arange(model.input_size * 3, dtype=torch.float32)
    x = x.reshape(3, model.input_size, 1)
    output = model({"insample_y": x})
    assert output.shape == (3, 5, 1)
    assert torch.isfinite(output).all()


def test_segrnn_state_dict_roundtrip(monkeypatch) -> None:
    _install_runtime_doubles(monkeypatch)
    model_class = runtime.get_segrnn_class()
    first = model_class(
        h=2,
        architecture_profile="compact",
        training_profile="smoke",
        loss=_PointLoss(),
        dropout=0.0,
    )
    second = model_class(
        h=2,
        architecture_profile="compact",
        training_profile="smoke",
        loss=_PointLoss(),
        dropout=0.0,
    )
    second.load_state_dict(first.state_dict(), strict=True)
    x = torch.randn(2, first.input_size, 1)
    first.eval()
    second.eval()
    assert torch.equal(first({"insample_y": x}), second({"insample_y": x}))


def test_segrnn_rejects_distribution_loss(monkeypatch) -> None:
    _install_runtime_doubles(monkeypatch)
    model_class = runtime.get_segrnn_class()
    with pytest.raises(ValueError, match="point training losses only"):
        model_class(
            h=1,
            architecture_profile="compact",
            training_profile="smoke",
            loss=_DistributionLoss(),
        )


def test_auto_segrnn_ray_and_optuna_configs(monkeypatch) -> None:
    _install_runtime_doubles(monkeypatch)
    auto_class = runtime.get_auto_segrnn_class()
    ray_model = auto_class(h=1, backend="ray", loss=_PointLoss())
    assert ray_model.cls_model.__name__ == "SegRNN"
    assert isinstance(ray_model.search_alg, _BasicVariantGenerator)
    optuna_model = auto_class(h=1, backend="optuna", loss=_PointLoss())
    assert callable(optuna_model.config)
    assert isinstance(optuna_model.search_alg, _RandomSampler)


def test_runtime_classes_have_stable_module_identity(monkeypatch) -> None:
    _install_runtime_doubles(monkeypatch)
    model_class = runtime.get_segrnn_class()
    auto_class = runtime.get_auto_segrnn_class()
    assert model_class.__module__ == runtime.__name__
    assert auto_class.__module__ == runtime.__name__
    assert runtime.get_segrnn_class() is model_class
    assert runtime.get_auto_segrnn_class() is auto_class

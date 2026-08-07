from __future__ import annotations

from types import SimpleNamespace

import torch
from torch import nn
from torch.nn import functional

from loto.neuralforecast.auto_frets import runtime


class PointLoss:
    outputsize_multiplier = 1


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
        return config


class Search:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class Tune:
    @staticmethod
    def choice(value):
        return ("choice", value)

    @staticmethod
    def loguniform(low, high):
        return ("loguniform", low, high)

    @staticmethod
    def randint(low, high):
        return ("randint", low, high)


def test_runtime_class_identity_is_stable(monkeypatch) -> None:
    runtime._reset_runtime_classes_for_tests()
    dependencies = {
        "BaseAuto": FakeBaseAuto,
        "BaseModel": FakeBaseModel,
        "BasicVariantGenerator": Search,
        "RandomSampler": Search,
        "functional": functional,
        "losses": Losses,
        "nn": nn,
        "torch": torch,
        "tune": Tune,
    }
    monkeypatch.setattr(runtime, "_load_runtime_dependencies", lambda: dependencies)
    first_model = runtime.get_frets_class()
    second_model = runtime.get_frets_class()
    first_auto = runtime.get_auto_frets_class()
    second_auto = runtime.get_auto_frets_class()
    assert first_model is second_model
    assert first_auto is second_auto
    assert first_model.__name__ == "FreTS"
    assert first_auto.__name__ == "AutoFreTS"
    instance = runtime.construct_auto_frets(h=1, backend="ray")
    assert instance.loto_model_id == "nf-local-auto-frets"
    runtime._reset_runtime_classes_for_tests()


def test_runtime_dependency_status_is_explicit(monkeypatch) -> None:
    availability = {
        "neuralforecast": True,
        "optuna": False,
        "ray": True,
        "torch": True,
    }
    monkeypatch.setattr(
        runtime.importlib.util,
        "find_spec",
        lambda name: SimpleNamespace() if availability[name] else None,
    )
    assert runtime.runtime_dependency_status() == availability

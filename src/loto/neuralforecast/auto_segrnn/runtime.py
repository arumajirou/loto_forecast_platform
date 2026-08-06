"""Dependency-lazy NeuralForecast SegRNN and AutoSegRNN classes."""

from __future__ import annotations

import importlib.util
from threading import RLock
from typing import Any

from .auto import build_auto_segrnn_class
from .model import build_segrnn_class

_RUNTIME_LOCK = RLock()
_RUNTIME_CLASSES: tuple[type[Any], type[Any]] | None = None
_REQUIRED_MODULES = ("neuralforecast", "optuna", "ray", "torch")


class RuntimeDependencyError(RuntimeError):
    """Raised when an executable AutoSegRNN dependency is unavailable."""


def runtime_dependency_status() -> dict[str, bool]:
    return {
        name: importlib.util.find_spec(name) is not None
        for name in _REQUIRED_MODULES
    }


def _load_runtime_dependencies() -> dict[str, Any]:
    status = runtime_dependency_status()
    missing = sorted(
        name for name, available in status.items() if not available
    )
    if missing:
        raise RuntimeDependencyError(
            "AutoSegRNN runtime dependencies are unavailable: "
            + ", ".join(missing)
        )

    import torch
    import torch.nn as nn
    from neuralforecast.common._base_auto import BaseAuto
    from neuralforecast.common._base_model import BaseModel
    from neuralforecast.losses import pytorch as losses
    from optuna.samplers import RandomSampler
    from ray import tune
    from ray.tune.search.basic_variant import BasicVariantGenerator

    return {
        "BaseAuto": BaseAuto,
        "BaseModel": BaseModel,
        "BasicVariantGenerator": BasicVariantGenerator,
        "RandomSampler": RandomSampler,
        "losses": losses,
        "nn": nn,
        "torch": torch,
        "tune": tune,
    }


def _build_runtime_classes() -> tuple[type[Any], type[Any]]:
    global _RUNTIME_CLASSES
    with _RUNTIME_LOCK:
        if _RUNTIME_CLASSES is not None:
            return _RUNTIME_CLASSES

        deps = _load_runtime_dependencies()
        segrnn_class = build_segrnn_class(
            base_model=deps["BaseModel"],
            losses=deps["losses"],
            nn=deps["nn"],
            torch=deps["torch"],
            module_name=__name__,
        )
        auto_class = build_auto_segrnn_class(
            base_auto=deps["BaseAuto"],
            basic_variant_generator=deps["BasicVariantGenerator"],
            random_sampler=deps["RandomSampler"],
            losses=deps["losses"],
            segrnn_class=segrnn_class,
            tune=deps["tune"],
            module_name=__name__,
        )
        globals()["SegRNN"] = segrnn_class
        globals()["AutoSegRNN"] = auto_class
        _RUNTIME_CLASSES = (segrnn_class, auto_class)
        return _RUNTIME_CLASSES


def get_segrnn_class() -> type[Any]:
    return _build_runtime_classes()[0]


def get_auto_segrnn_class() -> type[Any]:
    return _build_runtime_classes()[1]


def construct_auto_segrnn(**kwargs: Any) -> Any:
    return get_auto_segrnn_class()(**kwargs)


def __getattr__(name: str) -> Any:
    if name == "SegRNN":
        return get_segrnn_class()
    if name == "AutoSegRNN":
        return get_auto_segrnn_class()
    raise AttributeError(name)


def _reset_runtime_classes_for_tests() -> None:
    global _RUNTIME_CLASSES
    with _RUNTIME_LOCK:
        _RUNTIME_CLASSES = None
        globals().pop("SegRNN", None)
        globals().pop("AutoSegRNN", None)


__all__ = [
    "AutoSegRNN",
    "RuntimeDependencyError",
    "SegRNN",
    "construct_auto_segrnn",
    "get_auto_segrnn_class",
    "get_segrnn_class",
    "runtime_dependency_status",
]

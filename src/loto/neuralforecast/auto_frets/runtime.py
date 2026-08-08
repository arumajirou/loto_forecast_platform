"""Dependency-lazy NeuralForecast FreTS and AutoFreTS classes."""

from __future__ import annotations

import importlib.util
from threading import RLock
from typing import Any

from .auto import build_auto_frets_class
from .model import build_frets_class

_RUNTIME_LOCK = RLock()
_RUNTIME_CLASSES: tuple[type[Any], type[Any]] | None = None
_REQUIRED_MODULES = ("neuralforecast", "optuna", "ray", "torch")


class RuntimeDependencyError(RuntimeError):
    """Raised when an executable AutoFreTS dependency is unavailable."""


def runtime_dependency_status() -> dict[str, bool]:
    return {name: importlib.util.find_spec(name) is not None for name in _REQUIRED_MODULES}


def _load_runtime_dependencies() -> dict[str, Any]:
    status = runtime_dependency_status()
    missing = sorted(name for name, available in status.items() if not available)
    if missing:
        raise RuntimeDependencyError(
            "AutoFreTS runtime dependencies are unavailable: " + ", ".join(missing)
        )

    import torch
    import torch.nn as nn
    import torch.nn.functional as functional
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
        "functional": functional,
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
        frets_class = build_frets_class(
            base_model=deps["BaseModel"],
            functional=deps["functional"],
            losses=deps["losses"],
            nn=deps["nn"],
            torch=deps["torch"],
            module_name=__name__,
        )
        auto_class = build_auto_frets_class(
            base_auto=deps["BaseAuto"],
            basic_variant_generator=deps["BasicVariantGenerator"],
            frets_class=frets_class,
            losses=deps["losses"],
            random_sampler=deps["RandomSampler"],
            tune=deps["tune"],
            module_name=__name__,
        )
        globals()["FreTS"] = frets_class
        globals()["AutoFreTS"] = auto_class
        _RUNTIME_CLASSES = (frets_class, auto_class)
        return _RUNTIME_CLASSES


def get_frets_class() -> type[Any]:
    return _build_runtime_classes()[0]


def get_auto_frets_class() -> type[Any]:
    return _build_runtime_classes()[1]


def construct_auto_frets(**kwargs: Any) -> Any:
    return get_auto_frets_class()(**kwargs)


def __getattr__(name: str) -> Any:
    if name == "FreTS":
        return get_frets_class()
    if name == "AutoFreTS":
        return get_auto_frets_class()
    raise AttributeError(name)


def _reset_runtime_classes_for_tests() -> None:
    global _RUNTIME_CLASSES
    with _RUNTIME_LOCK:
        _RUNTIME_CLASSES = None
        globals().pop("FreTS", None)
        globals().pop("AutoFreTS", None)


__all__ = [
    "AutoFreTS",
    "FreTS",
    "RuntimeDependencyError",
    "construct_auto_frets",
    "get_auto_frets_class",
    "get_frets_class",
    "runtime_dependency_status",
]

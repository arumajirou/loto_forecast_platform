"""Install training-worker evidence without moving stable database campaign classes."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import ModuleType
from typing import Any

from .training_worker_evidence import (
    configure_training_evidence,
    training_evidence_auto_class,
)


@contextmanager
def _patched_auto_class(model_name: str) -> Iterator[None]:
    import neuralforecast.auto as auto_module

    original = getattr(auto_module, model_name, None)
    if original is None:
        raise ValueError(f"NeuralForecast does not expose {model_name}")
    setattr(auto_module, model_name, training_evidence_auto_class(original))
    try:
        yield
    finally:
        setattr(auto_module, model_name, original)


def _context_values(facade: ModuleType, *, backend: str, model_name: str) -> dict[str, Any]:
    context = facade._CONTEXT.get()
    if context is None:
        raise RuntimeError("training-evidence facade has no database execution context")
    config = context.config
    explicit = getattr(config, "require_gpu_execution", None)
    require_gpu = bool(getattr(config, "gpus", 0) > 0 if explicit is None else explicit)
    return {
        "backend": backend,
        "model_name": model_name,
        "model_id": getattr(context.spec, "model_id", None),
        "require_gpu": require_gpu,
    }


def install(facade: ModuleType) -> None:
    """Wrap constructor boundaries idempotently; execution remains under facade RLock."""

    if getattr(facade, "_loto_training_evidence_installed", False):
        return
    original_construct = facade._construct_interceptor
    original_hint = facade._construct_auto_hint

    def construct_interceptor(plan: Any) -> Any:
        model_name = str(plan.model_name)
        with _patched_auto_class(model_name):
            model = original_construct(plan)
        return configure_training_evidence(
            model,
            **_context_values(facade, backend=str(plan.backend), model_name=model_name),
        )

    def construct_auto_hint(config: Any, panel: Any):
        with _patched_auto_class("AutoHINT"):
            result = original_hint(config, panel)
        model, *remaining = result
        configured = configure_training_evidence(
            model,
            **_context_values(facade, backend="ray", model_name="AutoHINT"),
        )
        return (configured, *remaining)

    facade._construct_interceptor = construct_interceptor
    facade._construct_auto_hint = construct_auto_hint
    facade._loto_training_evidence_installed = True

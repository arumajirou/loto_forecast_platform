"""Install training-worker evidence without moving stable database campaign classes."""

from __future__ import annotations

from types import ModuleType
from typing import Any

from .training_worker_evidence import (
    configure_training_evidence,
    training_evidence_auto_class,
)


def _instrument_instance(model: Any) -> Any:
    """Attach the training-evidence mixin without mutating NeuralForecast globals.

    NeuralForecast AutoModel constructors use expressions such as
    ``super(AutoDLinear, self)``. Replacing ``neuralforecast.auto.AutoDLinear``
    with a dynamic subclass therefore changes the global resolved by that method and
    breaks constructor MRO. Construct the official class first, then switch only the
    resulting instance to the pickle-addressable instrumentation subclass before fit.
    """

    instrumented = training_evidence_auto_class(type(model))
    if not isinstance(model, instrumented):
        try:
            model.__class__ = instrumented
        except TypeError as exc:
            raise RuntimeError(
                "NeuralForecast AutoModel instance cannot be instrumented without "
                "mutating the official module class"
            ) from exc
    return model


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


def _record_resolved_certification_parameters(
    facade: ModuleType,
    *,
    plan: Any | None = None,
    random_seed: int | None = None,
    precision: str | None = None,
) -> None:
    """Persist the effective model controls for the later certification call."""

    context = facade._CONTEXT.get()
    if context is None:
        return

    resolved_seed = int(context.config.random_seed if random_seed is None else random_seed)
    resolved_precision = str(context.config.precision if precision is None else precision)

    if plan is not None:
        resolved_precision = str(getattr(plan, "precision", resolved_precision))
        plan_config = getattr(plan, "config", None)
        if isinstance(plan_config, dict) and "random_seed" in plan_config:
            try:
                resolved_seed = int(plan_config["random_seed"])
            except (TypeError, ValueError):
                pass

    context._loto_resolved_random_seed = resolved_seed
    context._loto_resolved_precision = resolved_precision


def _install_certification_parameter_bridge(facade: ModuleType) -> None:
    """Propagate resolved model seed/precision into runtime-certification evidence."""

    core = getattr(facade, "_CORE", None)
    if core is None or getattr(core, "_loto_certification_parameter_bridge_installed", False):
        return
    original = core.certify_saved_runtime

    def certify_saved_runtime(*args: Any, **kwargs: Any) -> Any:
        context = facade._CONTEXT.get()
        if context is not None:
            resolved_seed = getattr(
                context,
                "_loto_resolved_random_seed",
                int(context.config.random_seed),
            )
            resolved_precision = getattr(
                context,
                "_loto_resolved_precision",
                str(context.config.precision),
            )
            kwargs.setdefault("random_seed", int(resolved_seed))
            kwargs.setdefault("precision", str(resolved_precision))
        return original(*args, **kwargs)

    core._loto_certification_parameter_bridge_original = original
    core.certify_saved_runtime = certify_saved_runtime
    core._loto_certification_parameter_bridge_installed = True


def install(facade: ModuleType) -> None:
    """Wrap constructor/certification boundaries idempotently under the facade lock."""

    if getattr(facade, "_loto_training_evidence_installed", False):
        _install_certification_parameter_bridge(facade)
        return
    original_construct = facade._construct_interceptor
    original_hint = facade._construct_auto_hint

    def construct_interceptor(plan: Any) -> Any:
        model_name = str(plan.model_name)
        _record_resolved_certification_parameters(facade, plan=plan)
        model = _instrument_instance(original_construct(plan))
        return configure_training_evidence(
            model,
            **_context_values(facade, backend=str(plan.backend), model_name=model_name),
        )

    def construct_auto_hint(config: Any, panel: Any):
        _record_resolved_certification_parameters(
            facade,
            random_seed=int(config.random_seed),
            precision=str(config.precision),
        )
        result = original_hint(config, panel)
        model, *remaining = result
        configured = configure_training_evidence(
            _instrument_instance(model),
            **_context_values(facade, backend="ray", model_name="AutoHINT"),
        )
        return (configured, *remaining)

    facade._construct_interceptor = construct_interceptor
    facade._construct_auto_hint = construct_auto_hint

    # The persistence installer has already rebound the stable core AutoHINT route to
    # the facade function object. Rebind it again after wrapping so AutoHINT receives
    # the same in-worker evidence instrumentation as the regular AutoModel path.
    core = getattr(facade, "_CORE", None)
    if core is not None:
        core._construct_auto_hint = construct_auto_hint

    _install_certification_parameter_bridge(facade)
    facade._loto_training_evidence_installed = True

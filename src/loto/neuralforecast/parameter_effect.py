"""Helpers for one-factor-at-a-time NeuralForecast parameter effect audits.

The existing AutoModel request API treats an explicit ``config`` mapping as a
complete model configuration.  That is appropriate for fixed-config execution,
but not for sensitivity experiments where one parameter should be changed while
NeuralForecast's official default search space remains intact.

This module provides an explicit overlay path for that experiment use case.  It
keeps the official default search space, fixes experiment controls such as seed
and precision, and then overlays only the requested parameter values.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from loto.models.neuralforecast_adapter import (
    AutoModelPlan,
    AutoModelRequest,
    resolve_auto_model_plan,
)

_CONSTRUCTOR_ONLY_KEYS = frozenset({"n_series"})
_UNSUPPORTED_KEYS = frozenset({"num_workers", "num_workers_loader"})


@dataclass(frozen=True)
class ParameterEffectCase:
    """One controlled parameter variant for an effect audit."""

    parameter: str
    value: Any
    overrides: dict[str, Any]
    plan: AutoModelPlan


def resolve_overlay_auto_model_plan(
    request: AutoModelRequest,
    overrides: Mapping[str, Any],
) -> AutoModelPlan:
    """Resolve a plan that preserves the official search space plus overrides.

    ``AutoModelRequest.config`` is intentionally not reused here because that
    field means a complete fixed model config in the regular campaign path.
    Parameter-effect experiments instead start from the dependency-provided
    default search space and overlay only the requested values.
    """

    if request.config:
        raise ValueError(
            "parameter-effect overlay requires request.config to be empty; "
            "put experimental values in overrides"
        )

    frozen = dict(overrides)
    constructor_only = sorted(_CONSTRUCTOR_ONLY_KEYS.intersection(frozen))
    if constructor_only:
        raise ValueError(
            f"constructor-only parameters must be supplied on AutoModelRequest: {constructor_only}"
        )
    unsupported = sorted(_UNSUPPORTED_KEYS.intersection(frozen))
    if unsupported:
        raise ValueError(f"unsupported NeuralForecast parameters: {unsupported}")

    request_for_controls = request
    if "random_seed" in frozen:
        request_for_controls = replace(
            request_for_controls,
            random_seed=int(frozen["random_seed"]),
        )
    if "precision" in frozen:
        request_for_controls = replace(
            request_for_controls,
            precision=str(frozen["precision"]),
        )
    if "early_stop_patience_steps" in frozen:
        request_for_controls = replace(
            request_for_controls,
            early_stop_patience_steps=int(frozen["early_stop_patience_steps"]),
        )

    base = resolve_auto_model_plan(replace(request_for_controls, config={}))
    merged_overrides = dict(base.default_config_overrides)
    merged_overrides.update(frozen)

    evidence_config = dict(base.config)
    evidence_config.update(frozen)

    return replace(
        base,
        config=evidence_config,
        default_config_overrides=merged_overrides,
        adjustments=(*base.adjustments, "partial_parameter_overlay"),
    )


def build_one_factor_cases(
    request: AutoModelRequest,
    *,
    parameter: str,
    values: Iterable[Any],
    control_overrides: Mapping[str, Any] | None = None,
) -> tuple[ParameterEffectCase, ...]:
    """Build deterministic one-factor-at-a-time plans.

    Every case receives the same controls and changes only ``parameter``.  This
    makes downstream differences attributable to that parameter when data,
    split, seed and runtime environment are held constant.
    """

    controls = dict(control_overrides or {})
    cases: list[ParameterEffectCase] = []
    for value in values:
        overrides = dict(controls)
        overrides[parameter] = value
        cases.append(
            ParameterEffectCase(
                parameter=parameter,
                value=value,
                overrides=overrides,
                plan=resolve_overlay_auto_model_plan(request, overrides),
            )
        )
    if not cases:
        raise ValueError("parameter effect audit requires at least one value")
    return tuple(cases)

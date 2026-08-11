"""Deterministic placebo-event falsification for event hypotheses."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from loto.causal.event_study import _series, _validate_window, _window_effect


class PlaceboEventResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method: Literal["placebo_event_window_test"] = "placebo_event_window_test"
    event_index: int = Field(ge=1)
    observed_effect: float
    placebo_effects: tuple[float, ...]
    placebo_indices: tuple[int, ...]
    placebo_p_value: float = Field(ge=0.0, le=1.0)
    alpha: float = Field(gt=0.0, lt=1.0)
    falsification_passed: bool
    seed: int
    causal_claim_eligible: Literal[False] = False
    interpretation: str = (
        "placebo extremeness is a falsification diagnostic only and cannot establish causality"
    )


def _effect_only(
    treated: np.ndarray,
    *,
    event_index: int,
    pre_window: int,
    post_window: int,
    control: np.ndarray | None,
) -> float:
    components = _window_effect(
        treated,
        event_index=event_index,
        pre_window=pre_window,
        post_window=post_window,
        control=control,
    )
    treated_shift = components[2]
    control_shift = components[5]
    return float(treated_shift - (control_shift or 0.0))


def placebo_event_test(
    values: Sequence[float],
    *,
    event_index: int,
    pre_window: int,
    post_window: int,
    control_values: Sequence[float] | None = None,
    exclusion_radius: int | None = None,
    max_placebos: int = 200,
    seed: int = 1,
    alpha: float = 0.05,
) -> PlaceboEventResult:
    """Compare the declared event effect with temporally valid fake event locations.

    Placebo locations near the declared event are excluded by default to avoid contaminating the
    reference distribution with the same transition. Sampling is deterministic for a fixed seed.
    """
    treated = _series(values, name="values")
    _validate_window(int(treated.size), event_index, pre_window, post_window)
    if isinstance(max_placebos, bool) or not isinstance(max_placebos, int) or max_placebos < 1:
        raise ValueError("max_placebos must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if not math.isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be finite and in (0, 1)")

    control: np.ndarray | None = None
    if control_values is not None:
        control = _series(control_values, name="control_values")
        if control.size != treated.size:
            raise ValueError("control_values must have the same length as values")

    radius = max(pre_window, post_window) if exclusion_radius is None else exclusion_radius
    if isinstance(radius, bool) or not isinstance(radius, int) or radius < 0:
        raise ValueError("exclusion_radius must be a non-negative integer")

    valid_indices = [
        index
        for index in range(pre_window, int(treated.size) - post_window + 1)
        if abs(index - event_index) > radius
    ]
    if not valid_indices:
        raise ValueError("no valid placebo event indices remain after exclusion")

    rng = np.random.default_rng(seed)
    if len(valid_indices) > max_placebos:
        selected = sorted(
            int(value)
            for value in rng.choice(valid_indices, size=max_placebos, replace=False).tolist()
        )
    else:
        selected = valid_indices

    observed_effect = _effect_only(
        treated,
        event_index=event_index,
        pre_window=pre_window,
        post_window=post_window,
        control=control,
    )
    placebo_effects = tuple(
        _effect_only(
            treated,
            event_index=index,
            pre_window=pre_window,
            post_window=post_window,
            control=control,
        )
        for index in selected
    )
    exceedances = sum(abs(effect) >= abs(observed_effect) - 1e-15 for effect in placebo_effects)
    p_value = (exceedances + 1.0) / (len(placebo_effects) + 1.0)

    return PlaceboEventResult(
        event_index=event_index,
        observed_effect=observed_effect,
        placebo_effects=placebo_effects,
        placebo_indices=tuple(selected),
        placebo_p_value=float(p_value),
        alpha=alpha,
        falsification_passed=p_value <= alpha,
        seed=seed,
    )

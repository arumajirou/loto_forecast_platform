"""Guarded event-window effect estimation.

A raw pre/post difference is descriptive. A control-adjusted difference can only become eligible
for guarded causal interpretation when a matching ``controlled_event_study`` identification plan
also passes the explicit identification gate. Eligibility is not proof of causality.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from loto.causal.contracts import IdentificationPlan, assess_identification


class EventEffectResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method: Literal["event_window_mean_shift"] = "event_window_mean_shift"
    event_index: int = Field(ge=1)
    pre_window: int = Field(ge=2)
    post_window: int = Field(ge=2)
    treated_pre_mean: float
    treated_post_mean: float
    treated_mean_shift: float
    control_pre_mean: float | None = None
    control_post_mean: float | None = None
    control_mean_shift: float | None = None
    effect: float
    standard_error: float | None
    identification_hypothesis_id: str | None = None
    causal_claim_eligible: bool = False
    interpretation: str


def _series(values: Sequence[float], *, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if array.size < 4:
        raise ValueError(f"{name} must contain at least four observations")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")
    return array


def _validate_window(
    n: int,
    event_index: int,
    pre_window: int,
    post_window: int,
) -> None:
    for name, value in (
        ("event_index", event_index),
        ("pre_window", pre_window),
        ("post_window", post_window),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
    if pre_window < 2 or post_window < 2:
        raise ValueError("pre_window and post_window must both be >= 2")
    if event_index - pre_window < 0:
        raise ValueError("pre window extends before the start of the series")
    if event_index + post_window > n:
        raise ValueError("post window extends beyond the end of the series")


def _window_effect(
    treated: np.ndarray,
    *,
    event_index: int,
    pre_window: int,
    post_window: int,
    control: np.ndarray | None,
) -> tuple[float, float, float, float | None, float | None, float | None, float | None]:
    treated_pre = treated[event_index - pre_window : event_index]
    treated_post = treated[event_index : event_index + post_window]
    treated_pre_mean = float(treated_pre.mean())
    treated_post_mean = float(treated_post.mean())
    treated_shift = treated_post_mean - treated_pre_mean

    treated_variance_term = float(np.var(treated_pre, ddof=1) / treated_pre.size) + float(
        np.var(treated_post, ddof=1) / treated_post.size
    )
    if control is None:
        standard_error = math.sqrt(treated_variance_term) if treated_variance_term > 0.0 else None
        return (
            treated_pre_mean,
            treated_post_mean,
            treated_shift,
            None,
            None,
            None,
            standard_error,
        )

    control_pre = control[event_index - pre_window : event_index]
    control_post = control[event_index : event_index + post_window]
    control_pre_mean = float(control_pre.mean())
    control_post_mean = float(control_post.mean())
    control_shift = control_post_mean - control_pre_mean
    control_variance_term = float(np.var(control_pre, ddof=1) / control_pre.size) + float(
        np.var(control_post, ddof=1) / control_post.size
    )
    total_variance = treated_variance_term + control_variance_term
    standard_error = math.sqrt(total_variance) if total_variance > 0.0 else None
    return (
        treated_pre_mean,
        treated_post_mean,
        treated_shift,
        control_pre_mean,
        control_post_mean,
        control_shift,
        standard_error,
    )


def estimate_pre_post_effect(
    values: Sequence[float],
    *,
    event_index: int,
    pre_window: int,
    post_window: int,
    control_values: Sequence[float] | None = None,
    identification_plan: IdentificationPlan | None = None,
) -> EventEffectResult:
    """Estimate a pre/post level shift, optionally net of a declared control series."""
    treated = _series(values, name="values")
    _validate_window(int(treated.size), event_index, pre_window, post_window)

    control: np.ndarray | None = None
    if control_values is not None:
        control = _series(control_values, name="control_values")
        if control.size != treated.size:
            raise ValueError("control_values must have the same length as values")

    (
        treated_pre_mean,
        treated_post_mean,
        treated_shift,
        control_pre_mean,
        control_post_mean,
        control_shift,
        standard_error,
    ) = _window_effect(
        treated,
        event_index=event_index,
        pre_window=pre_window,
        post_window=post_window,
        control=control,
    )
    effect = treated_shift - (control_shift or 0.0)

    hypothesis_id: str | None = None
    eligible = False
    interpretation = "descriptive pre/post association only; causal claim must remain closed"
    if identification_plan is not None:
        hypothesis_id = identification_plan.hypothesis_id
        assessment = assess_identification(identification_plan)
        eligible = (
            assessment.causal_claim_eligible
            and identification_plan.design == "controlled_event_study"
            and control is not None
        )
        if eligible:
            interpretation = (
                "control-adjusted event effect eligible for guarded causal interpretation; "
                "negative-control and model-assumption checks still required"
            )
        elif (
            assessment.causal_claim_eligible
            and identification_plan.design != "controlled_event_study"
        ):
            interpretation = (
                "identification plan passes its general gate, but this v1 estimator does not "
                "implement the declared design; causal claim remains closed"
            )
        else:
            interpretation = assessment.interpretation

    return EventEffectResult(
        event_index=event_index,
        pre_window=pre_window,
        post_window=post_window,
        treated_pre_mean=treated_pre_mean,
        treated_post_mean=treated_post_mean,
        treated_mean_shift=treated_shift,
        control_pre_mean=control_pre_mean,
        control_post_mean=control_post_mean,
        control_mean_shift=control_shift,
        effect=float(effect),
        standard_error=standard_error,
        identification_hypothesis_id=hypothesis_id,
        causal_claim_eligible=eligible,
        interpretation=interpretation,
    )

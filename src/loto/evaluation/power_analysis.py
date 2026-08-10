"""Pre-experiment power and minimum-detectable-effect planning.

This module deliberately reports a *normal-approximation paired-score* calculation rather than
pretending that Hit@±1 elements are independent Bernoulli trials. Callers provide the standard
deviation of the per-draw paired score difference from development/pilot evidence or a declared
simulation model. The calculation is planning evidence, not a significance test on Holdout or
Prospective data.
"""

from __future__ import annotations

import math
from statistics import NormalDist

from pydantic import BaseModel, ConfigDict, Field, model_validator

POWER_METHOD = "paired-score-normal-approximation-v1"


class PowerPlan(BaseModel):
    """Immutable planning inputs for one-sided positive paired improvement detection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    alpha: float = Field(default=0.05, gt=0.0, lt=1.0)
    target_power: float = Field(default=0.80, gt=0.0, lt=1.0)
    multiplicity: int = Field(default=1, ge=1)
    alternative: str = "candidate_minus_reference_gt_zero"

    @property
    def adjusted_alpha(self) -> float:
        """Conservative family-wise planning alpha using Bonferroni."""
        return self.alpha / self.multiplicity

    @model_validator(mode="after")
    def validate_tail(self) -> PowerPlan:
        if self.alternative != "candidate_minus_reference_gt_zero":
            raise ValueError("only the pre-specified one-sided positive alternative is supported")
        return self


class PowerResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method: str = POWER_METHOD
    alpha: float
    adjusted_alpha: float
    target_power: float
    multiplicity: int
    score_sd: float
    effect: float | None = None
    n_draws: int | None = None
    minimum_detectable_effect: float | None = None
    required_draws: int | None = None
    assumptions: tuple[str, ...] = (
        "per-draw paired score differences are independent enough for "
        "planning-scale normal approximation",
        "score_sd is fixed before the target evaluation window",
        "this result is planning evidence, not a realized p-value or promotion decision",
    )


def _z(probability: float) -> float:
    if not 0.0 < probability < 1.0:
        raise ValueError("normal quantile probability must be in (0, 1)")
    return NormalDist().inv_cdf(probability)


def _validate_score_sd(score_sd: float) -> float:
    value = float(score_sd)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("score_sd must be finite and > 0")
    return value


def required_paired_draws(
    effect: float,
    score_sd: float,
    *,
    plan: PowerPlan | None = None,
) -> PowerResult:
    """Required draws for a one-sided paired mean improvement under the declared approximation."""
    resolved = plan or PowerPlan()
    delta = float(effect)
    sd = _validate_score_sd(score_sd)
    if not math.isfinite(delta) or delta <= 0.0:
        raise ValueError("effect must be finite and > 0")
    critical = _z(1.0 - resolved.adjusted_alpha) + _z(resolved.target_power)
    required = int(math.ceil((critical * sd / delta) ** 2))
    return PowerResult(
        alpha=resolved.alpha,
        adjusted_alpha=resolved.adjusted_alpha,
        target_power=resolved.target_power,
        multiplicity=resolved.multiplicity,
        score_sd=sd,
        effect=delta,
        required_draws=max(required, 1),
    )


def minimum_detectable_effect(
    n_draws: int,
    score_sd: float,
    *,
    plan: PowerPlan | None = None,
) -> PowerResult:
    """Smallest positive paired mean effect detectable at the requested planning power."""
    resolved = plan or PowerPlan()
    if isinstance(n_draws, bool) or not isinstance(n_draws, int) or n_draws < 1:
        raise ValueError("n_draws must be a positive integer")
    sd = _validate_score_sd(score_sd)
    critical = _z(1.0 - resolved.adjusted_alpha) + _z(resolved.target_power)
    effect = critical * sd / math.sqrt(n_draws)
    return PowerResult(
        alpha=resolved.alpha,
        adjusted_alpha=resolved.adjusted_alpha,
        target_power=resolved.target_power,
        multiplicity=resolved.multiplicity,
        score_sd=sd,
        n_draws=n_draws,
        minimum_detectable_effect=float(effect),
    )


def power_curve(
    draw_counts: tuple[int, ...],
    score_sd: float,
    *,
    plan: PowerPlan | None = None,
) -> list[dict[str, float | int | str]]:
    """Return a deterministic MDE curve for pre-specified draw counts."""
    if not draw_counts or len(set(draw_counts)) != len(draw_counts):
        raise ValueError("draw_counts must be non-empty and unique")
    for index, n_draws in enumerate(draw_counts):
        if isinstance(n_draws, bool) or not isinstance(n_draws, int) or n_draws < 1:
            raise ValueError(f"draw_counts[{index}] must be a positive integer")
    if tuple(sorted(draw_counts)) != draw_counts:
        raise ValueError("draw_counts must be sorted")
    rows: list[dict[str, float | int | str]] = []
    for n_draws in draw_counts:
        result = minimum_detectable_effect(n_draws, score_sd, plan=plan)
        rows.append(
            {
                "method": result.method,
                "n_draws": n_draws,
                "minimum_detectable_effect": float(result.minimum_detectable_effect),
                "adjusted_alpha": result.adjusted_alpha,
                "target_power": result.target_power,
            }
        )
    return rows

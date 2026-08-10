"""Theory-aware configuration guard for Hit@±tau targets.

The exact bound produced by :mod:`loto.evaluation.theory_general` is an optimum under the
specified IID-null distribution. It is deliberately not described as a universal ceiling for
all possible biased data-generating processes.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loto.evaluation.theory_general import theoretical_bounds
from loto.game.geometry import known_games


class ThresholdSemantics(StrEnum):
    ABSOLUTE = "absolute"
    EXCESS_VS_IID_NULL = "excess_vs_iid_null"


class TheoryThresholdStatus(StrEnum):
    VALID_WITHIN_NULL_REFERENCE = "VALID_WITHIN_NULL_REFERENCE"
    VALID_NULL_RELATIVE = "VALID_NULL_RELATIVE"
    EXCEEDS_NULL_CEILING = "EXCEEDS_NULL_CEILING"
    ALTERNATIVE_HYPOTHESIS_DECLARED = "ALTERNATIVE_HYPOTHESIS_DECLARED"


class TheoryAwareThreshold(BaseModel):
    """Result-affecting Hit@±tau threshold with explicit null semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    game: str
    tau: int = Field(default=1, ge=0)
    semantics: ThresholdSemantics = ThresholdSemantics.EXCESS_VS_IID_NULL
    target: float = Field(default=0.0, ge=-1.0, le=1.0)
    allow_above_null_ceiling: bool = False
    alternative_hypothesis: str | None = None

    @model_validator(mode="after")
    def fail_closed(self) -> TheoryAwareThreshold:
        if self.game not in set(known_games()):
            raise ValueError(f"unknown game: {self.game}")
        assessment = assess_threshold(self)
        implied = float(assessment["implied_absolute_target"])
        if not 0.0 <= implied <= 1.0:
            raise ValueError(
                "TARGET_OUTSIDE_PROBABILITY_RANGE: configured semantics imply an absolute "
                "Hit@±tau target outside [0, 1]"
            )
        if assessment["status"] == TheoryThresholdStatus.EXCEEDS_NULL_CEILING.value:
            raise ValueError(
                "EXCEEDS_NULL_CEILING: absolute Hit@±tau target is above the exact IID-null "
                "ceiling; declare an alternative hypothesis explicitly or use null-relative "
                "semantics"
            )
        if (
            self.semantics is ThresholdSemantics.ABSOLUTE
            and self.allow_above_null_ceiling
            and not (self.alternative_hypothesis or "").strip()
        ):
            raise ValueError(
                "alternative_hypothesis is required when allow_above_null_ceiling=true"
            )
        return self

    def assessment(self) -> dict[str, object]:
        return assess_threshold(self)


def assess_threshold(config: TheoryAwareThreshold) -> dict[str, object]:
    """Return the exact IID-null reference and the configured target semantics."""
    bounds = theoretical_bounds(config.game, tau=config.tau)
    ceiling = float(bounds.within_tau_ceiling)
    if config.semantics is ThresholdSemantics.EXCESS_VS_IID_NULL:
        status = TheoryThresholdStatus.VALID_NULL_RELATIVE
        implied_absolute = ceiling + float(config.target)
    elif float(config.target) <= ceiling:
        status = TheoryThresholdStatus.VALID_WITHIN_NULL_REFERENCE
        implied_absolute = float(config.target)
    elif config.allow_above_null_ceiling and (config.alternative_hypothesis or "").strip():
        status = TheoryThresholdStatus.ALTERNATIVE_HYPOTHESIS_DECLARED
        implied_absolute = float(config.target)
    else:
        status = TheoryThresholdStatus.EXCEEDS_NULL_CEILING
        implied_absolute = float(config.target)
    return {
        "game": config.game,
        "tau": config.tau,
        "semantics": config.semantics.value,
        "target": float(config.target),
        "iid_null_ceiling": ceiling,
        "implied_absolute_target": implied_absolute,
        "status": status.value,
        "allow_above_null_ceiling": config.allow_above_null_ceiling,
        "alternative_hypothesis": config.alternative_hypothesis,
        "interpretation": (
            "iid_null_ceiling is an exact optimum under the IID-null distribution; it is not a "
            "universal bound for every possible biased data-generating process"
        ),
    }

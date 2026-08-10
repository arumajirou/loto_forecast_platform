from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.evaluation.power_analysis import (
    POWER_METHOD,
    PowerPlan,
    minimum_detectable_effect,
    power_curve,
    required_paired_draws,
)


def test_required_draws_and_mde_are_algebraic_inverses_up_to_ceiling() -> None:
    plan = PowerPlan(alpha=0.05, target_power=0.8, multiplicity=1)
    required = required_paired_draws(0.02, 0.20, plan=plan)
    assert required.method == POWER_METHOD
    assert required.required_draws is not None

    mde = minimum_detectable_effect(required.required_draws, 0.20, plan=plan)
    assert mde.minimum_detectable_effect is not None
    assert mde.minimum_detectable_effect <= pytest.approx(0.02, abs=2e-4)


def test_more_draws_reduce_minimum_detectable_effect() -> None:
    rows = power_curve((50, 100, 400), 0.25)
    effects = [float(row["minimum_detectable_effect"]) for row in rows]
    assert effects[0] > effects[1] > effects[2]


def test_multiplicity_is_conservative() -> None:
    single = required_paired_draws(0.03, 0.2, plan=PowerPlan(multiplicity=1))
    many = required_paired_draws(0.03, 0.2, plan=PowerPlan(multiplicity=20))
    assert many.adjusted_alpha < single.adjusted_alpha
    assert many.required_draws is not None and single.required_draws is not None
    assert many.required_draws > single.required_draws


def test_power_plan_rejects_unsupported_two_sided_or_reverse_claims() -> None:
    with pytest.raises(ValidationError, match="one-sided positive"):
        PowerPlan(alternative="candidate_minus_reference_ne_zero")


def test_inputs_fail_closed() -> None:
    with pytest.raises(ValueError, match="effect"):
        required_paired_draws(0.0, 0.2)
    with pytest.raises(ValueError, match="score_sd"):
        required_paired_draws(0.01, 0.0)
    with pytest.raises(ValueError, match="positive integer"):
        minimum_detectable_effect(0, 0.2)
    with pytest.raises(ValueError, match="sorted"):
        power_curve((100, 50), 0.2)

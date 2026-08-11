from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from loto.causal.contracts import CausalDag, IdentificationPlan, assess_identification
from loto.causal.event_study import estimate_pre_post_effect
from loto.causal.negative_control import placebo_event_test


def _dag() -> CausalDag:
    return CausalDag(
        nodes=("confounder", "intervention", "outcome"),
        edges=(
            ("confounder", "intervention"),
            ("confounder", "outcome"),
            ("intervention", "outcome"),
        ),
    )


def _eligible_plan() -> IdentificationPlan:
    return IdentificationPlan(
        hypothesis_id="machine-change-effect-v1",
        dag=_dag(),
        exposure="intervention",
        outcome="outcome",
        adjustment_set=("confounder",),
        design="controlled_event_study",
        intervention_time_known=True,
        temporal_order_verified=True,
        confounders_declared=True,
        negative_control_pre_registered=True,
        no_concurrent_interventions_asserted=True,
        control_series_declared=True,
    )


def test_dag_rejects_cycles() -> None:
    with pytest.raises(ValidationError, match="directed cycle"):
        CausalDag(
            nodes=("a", "b", "c"),
            edges=(("a", "b"), ("b", "c"), ("c", "a")),
        )


def test_identification_fails_closed_until_all_requirements_are_declared() -> None:
    weak_plan = IdentificationPlan(
        hypothesis_id="association-only",
        dag=_dag(),
        exposure="intervention",
        outcome="outcome",
        design="pre_post_event",
    )
    weak = assess_identification(weak_plan)
    strong = assess_identification(_eligible_plan())

    assert weak.causal_claim_eligible is False
    assert weak.unmet_requirements
    assert "causal claim must remain closed" in weak.interpretation
    assert strong.causal_claim_eligible is True
    assert strong.unmet_requirements == ()


def test_event_effect_requires_control_and_matching_identification_plan() -> None:
    treated = np.concatenate([np.zeros(50), np.full(50, 5.0)])
    control = np.zeros(100)

    descriptive = estimate_pre_post_effect(
        treated,
        event_index=50,
        pre_window=15,
        post_window=15,
    )
    controlled = estimate_pre_post_effect(
        treated,
        event_index=50,
        pre_window=15,
        post_window=15,
        control_values=control,
        identification_plan=_eligible_plan(),
    )

    assert descriptive.effect == pytest.approx(5.0)
    assert descriptive.causal_claim_eligible is False
    assert controlled.effect == pytest.approx(5.0)
    assert controlled.control_mean_shift == pytest.approx(0.0)
    assert controlled.causal_claim_eligible is True
    assert controlled.identification_hypothesis_id == "machine-change-effect-v1"


def test_placebo_event_test_is_reproducible_and_not_itself_causal() -> None:
    values = np.concatenate([np.zeros(50), np.full(50, 7.0)])

    first = placebo_event_test(
        values,
        event_index=50,
        pre_window=10,
        post_window=10,
        max_placebos=20,
        seed=9,
        alpha=0.05,
    )
    second = placebo_event_test(
        values,
        event_index=50,
        pre_window=10,
        post_window=10,
        max_placebos=20,
        seed=9,
        alpha=0.05,
    )

    assert first == second
    assert first.observed_effect == pytest.approx(7.0)
    assert first.placebo_p_value <= 0.05
    assert first.falsification_passed is True
    assert first.causal_claim_eligible is False

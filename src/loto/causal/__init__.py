"""Fail-closed causal-identification and falsification primitives."""

from loto.causal.contracts import (
    CausalDag,
    IdentificationAssessment,
    IdentificationPlan,
    assess_identification,
)
from loto.causal.event_study import estimate_pre_post_effect
from loto.causal.negative_control import placebo_event_test

__all__ = [
    "CausalDag",
    "IdentificationAssessment",
    "IdentificationPlan",
    "assess_identification",
    "estimate_pre_post_effect",
    "placebo_event_test",
]

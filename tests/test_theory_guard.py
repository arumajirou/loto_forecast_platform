from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.autogluon_campaign.promotion_eligibility_contract import (
    PromotionPolicy,
    PromotionPolicyV2,
)
from loto.evaluation.theory_guard import TheoryAwareThreshold, ThresholdSemantics


def test_legacy_promotion_policy_keeps_historical_absolute_default() -> None:
    assert PromotionPolicy().hit_at_1_target == pytest.approx(0.90)


def test_v2_defaults_to_null_relative_target() -> None:
    policy = PromotionPolicyV2(game="numbers3")
    assessment = policy.theory_assessment()

    assert policy.hit_at_1_target == pytest.approx(0.0)
    assert policy.hit_at_1_target_semantics is ThresholdSemantics.EXCESS_VS_IID_NULL
    assert assessment["status"] == "VALID_NULL_RELATIVE"
    assert assessment["iid_null_ceiling"] == pytest.approx(0.3)
    assert assessment["implied_absolute_target"] == pytest.approx(0.3)


def test_unexplained_absolute_target_above_iid_null_ceiling_fails_closed() -> None:
    with pytest.raises(ValidationError, match="EXCEEDS_NULL_CEILING"):
        PromotionPolicyV2(
            game="numbers3",
            hit_at_1_target_semantics=ThresholdSemantics.ABSOLUTE,
            hit_at_1_target=0.90,
        )


def test_above_null_absolute_target_requires_explicit_alternative_hypothesis() -> None:
    with pytest.raises(ValidationError):
        PromotionPolicyV2(
            game="loto6",
            hit_at_1_target_semantics=ThresholdSemantics.ABSOLUTE,
            hit_at_1_target=0.90,
            allow_above_null_ceiling=True,
        )

    policy = PromotionPolicyV2(
        game="loto6",
        hit_at_1_target_semantics=ThresholdSemantics.ABSOLUTE,
        hit_at_1_target=0.90,
        allow_above_null_ceiling=True,
        alternative_hypothesis="persistent pre-specified non-IID draw-process bias",
    )
    assessment = policy.theory_assessment()
    assert assessment["status"] == "ALTERNATIVE_HYPOTHESIS_DECLARED"
    assert assessment["iid_null_ceiling"] == pytest.approx(0.23501935168651591)
    assert assessment["implied_absolute_target"] == pytest.approx(0.90)


def test_null_relative_target_is_not_mislabeled_as_universal_bound() -> None:
    assessment = TheoryAwareThreshold(
        game="loto7",
        semantics=ThresholdSemantics.EXCESS_VS_IID_NULL,
        target=0.01,
    ).assessment()
    assert assessment["iid_null_ceiling"] == pytest.approx(0.2922598539296832)
    assert assessment["implied_absolute_target"] == pytest.approx(0.3022598539296832)
    assert "not a universal bound" in str(assessment["interpretation"])


def test_null_relative_target_cannot_imply_probability_above_one() -> None:
    with pytest.raises(ValidationError, match="TARGET_OUTSIDE_PROBABILITY_RANGE"):
        TheoryAwareThreshold(
            game="numbers3",
            semantics=ThresholdSemantics.EXCESS_VS_IID_NULL,
            target=0.80,
        )


def test_unknown_game_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown game"):
        TheoryAwareThreshold(game="not-a-game")

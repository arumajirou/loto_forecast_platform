import pytest

from loto.moirai2_campaign.license_policy import LicensePolicyError, evaluate_license_lane


def test_research_lane_is_never_production_eligible() -> None:
    decision = evaluate_license_lane("personal_noncommercial_research")
    assert decision.research_only is True
    assert decision.production_champion_eligible is False
    assert decision.automatic_promotion is False


def test_commercial_lane_fails_closed() -> None:
    with pytest.raises(LicensePolicyError):
        evaluate_license_lane("commercial")

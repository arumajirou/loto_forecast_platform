import pytest

from loto.statsforecast.contracts import ExpectedStatus
from loto.statsforecast.inventory import MODEL_CONTRACTS, MODEL_NAMES, model_contract


def test_project_inventory_has_41_unique_models() -> None:
    assert len(MODEL_NAMES) == 41
    assert len(set(MODEL_NAMES)) == 41
    assert len(MODEL_CONTRACTS) == 41


def test_nan_model_is_expected_negative_and_not_champion() -> None:
    contract = model_contract("NaNModel")
    assert contract.expected_status is ExpectedStatus.EXPECTED_NEGATIVE_PASS
    assert contract.champion_eligible is False


def test_unknown_model_fails_closed() -> None:
    with pytest.raises(KeyError, match="unknown StatsForecast model"):
        model_contract("InventedModel")


def test_inventory_matches_upstream_2_1_1_surface() -> None:
    assert "ConformalSeasonalPool" in MODEL_NAMES
    assert "CES" not in MODEL_NAMES

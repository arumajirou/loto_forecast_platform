import pytest
from pydantic import ValidationError

from loto.statsforecast.contracts import CampaignConfig, GameGeometry, TimeAxisContract


def geometry() -> GameGeometry:
    return GameGeometry(
        game="numbers4",
        positions=("d1", "d2", "d3", "d4"),
        candidate_min=0,
        candidate_max=9,
        top_k=4,
    )


def test_draw_sequence_requires_integer_frequency() -> None:
    with pytest.raises(ValidationError, match="freq=1"):
        TimeAxisContract(freq="7D")


def test_campaign_forces_inner_single_thread() -> None:
    with pytest.raises(ValidationError, match="n_jobs=1"):
        CampaignConfig(geometry=geometry(), model_names=("Naive",), n_jobs=2)


def test_geometry_rejects_duplicate_positions() -> None:
    with pytest.raises(ValidationError, match="unique"):
        GameGeometry(
            game="x",
            positions=("n1", "n1"),
            candidate_min=1,
            candidate_max=10,
            top_k=2,
        )

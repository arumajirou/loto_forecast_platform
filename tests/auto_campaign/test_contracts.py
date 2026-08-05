from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.auto_campaign.contracts import CampaignConfig


def test_duplicate_seeds_rejected() -> None:
    with pytest.raises(ValidationError):
        CampaignConfig(data_path=Path("x.csv"), model_seeds=[1, 1])

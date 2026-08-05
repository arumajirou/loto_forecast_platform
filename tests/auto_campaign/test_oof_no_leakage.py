from pathlib import Path

import pandas as pd

from loto.auto_campaign.contracts import CampaignConfig
from loto.auto_campaign.data_tracks import oof_endpoints


def test_oof_stays_inside_train_partition() -> None:
    config = CampaignConfig(data_path=Path("unused.csv"))
    frame = pd.DataFrame({"x": range(200)})
    endpoints = oof_endpoints(frame, config)
    train_stop = len(frame) - config.split.validation_draws - config.split.holdout_draws
    assert len(endpoints) == config.split.oof_folds
    assert max(endpoints) < train_stop

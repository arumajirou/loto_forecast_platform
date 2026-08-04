from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from loto.auto_campaign.contracts import CampaignConfig
from loto.auto_campaign.data_tracks import load_miniloto


def test_draw_no_and_n_columns_are_normalized(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mini.csv"

    pd.DataFrame(
        {
            "game": ["mini", "mini"],
            "draw_no": [100, 101],
            "draw_date": ["2026-01-01", "2026-01-08"],
            "n1": [1, 2],
            "n2": [5, 6],
            "n3": [10, 11],
            "n4": [20, 21],
            "n5": [30, 31],
        }
    ).to_csv(path, index=False)

    payload = yaml.safe_load(
        Path("configs/auto_campaign/campaign.yaml").read_text(encoding="utf-8")
    )
    payload["data_path"] = str(path)
    payload["number_columns"] = ["P1", "P2", "P3", "P4", "P5"]
    payload["draw_id_candidates"] = ["draw_no"]
    payload["draw_index_candidates"] = ["draw_no"]

    config = CampaignConfig.model_validate(payload)
    frame, contract = load_miniloto(config)

    assert contract.draw_id_column == "draw_no"
    assert contract.draw_index_column == "__draw_index__"
    assert list(frame["draw_no"].astype(str)) == ["100", "101"]
    assert list(frame["__draw_index__"]) == [100, 101]
    assert list(frame["P1"]) == [1, 2]
    assert list(frame["P5"]) == [30, 31]

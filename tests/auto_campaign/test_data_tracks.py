from pathlib import Path

import pandas as pd

from loto.auto_campaign.contracts import CampaignConfig
from loto.auto_campaign.data_tracks import build_panel, load_miniloto


def test_panel_is_time_ordered_and_leakage_safe(tmp_path: Path) -> None:
    path = tmp_path / "mini.csv"
    pd.DataFrame(
        {
            "draw_id": ["3", "1", "2"],
            "draw_index": [3, 1, 2],
            "P1": [3, 1, 2],
            "P2": [4, 2, 3],
            "P3": [5, 3, 4],
            "P4": [6, 4, 5],
            "P5": [7, 5, 6],
        }
    ).to_csv(path, index=False)
    config = CampaignConfig(data_path=path)
    frame, contract = load_miniloto(config)
    assert frame[contract.draw_index_column].tolist() == [1, 2, 3]
    panel = build_panel(frame, contract, track="u_shared")
    assert (
        panel.groupby("unique_id")["ds"].apply(lambda values: values.is_monotonic_increasing).all()
    )  # noqa: E501

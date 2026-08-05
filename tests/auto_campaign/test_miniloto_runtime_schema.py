from __future__ import annotations

from pathlib import Path

import pandas as pd

from loto.auto_campaign.contracts import CampaignConfig
from loto.auto_campaign.data_tracks import load_miniloto


def test_runtime_schema_maps_n1_to_n5(tmp_path: Path) -> None:
    path = tmp_path / "mini.csv"
    pd.DataFrame(
        {
            "draw_no": [1, 2],
            "n1": [1, 2],
            "n2": [5, 6],
            "n3": [10, 11],
            "n4": [20, 21],
            "n5": [30, 31],
        }
    ).to_csv(path, index=False)

    config = CampaignConfig.model_validate(
        {
            "data_path": str(path),
            "number_columns": ["P1", "P2", "P3", "P4", "P5"],
            "draw_id_candidates": ["draw_no"],
            "draw_index_candidates": ["draw_no"],
        }
    )

    frame, _contract = load_miniloto(config)

    assert [column for column in frame.columns if column.startswith("P")] == [
        "P1",
        "P2",
        "P3",
        "P4",
        "P5",
    ]

from __future__ import annotations

import pandas as pd

from loto.adapters.timesfm25.contracts import GameGeometry
from loto.timesfm25_campaign.geometry import infer_position_columns, validate_geometry_columns


def test_position_columns_are_naturally_sorted() -> None:
    frame = pd.DataFrame({"n10": [1], "n2": [1], "n1": [1], "draw_no": [1]})
    assert infer_position_columns(frame) == ["n1", "n2", "n10"]


def test_geometry_accepts_loto7() -> None:
    geometry = GameGeometry(
        game_id="loto7",
        position_count=7,
        candidate_min=1,
        candidate_max=37,
        strictly_increasing=True,
    )
    validate_geometry_columns(geometry, [f"n{index}" for index in range(1, 8)])

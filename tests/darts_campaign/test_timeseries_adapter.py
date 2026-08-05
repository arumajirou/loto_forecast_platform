from __future__ import annotations

import pandas as pd
import pytest

from loto.darts_campaign.protocol import GameGeometry
from loto.darts_campaign.timeseries_adapter import build_position_local, validate_panel


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "draw_no": [10, 11, 12],
            "n1": [1, 2, 3],
            "n2": [4, 5, 6],
            "n3": [7, 8, 9],
            "n4": [0, 1, 2],
        }
    )


def _geometry() -> GameGeometry:
    return GameGeometry(game_id="numbers4", positions=4, min_value=0, max_value=9)


def test_position_local_shape_and_input_immutability() -> None:
    frame = _frame()
    before = frame.copy(deep=True)
    payload = build_position_local(frame, _geometry())
    assert len(payload.series) == 4
    assert all(len(series) == 3 for series in payload.series)
    assert list(payload.series[0].index) == [10, 11, 12]
    pd.testing.assert_frame_equal(frame, before)


def test_gap_is_rejected_without_repair() -> None:
    frame = _frame()
    frame.loc[2, "draw_no"] = 13
    with pytest.raises(ValueError, match="gap-free"):
        validate_panel(frame, _geometry())

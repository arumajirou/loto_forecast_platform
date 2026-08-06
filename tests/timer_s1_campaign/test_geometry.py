from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from loto.adapters.timer_s1.contracts import Game, HistoryRow, TimelineMode
from loto.timer_s1_campaign.geometry import compile_history, position_count_for_game


@pytest.mark.parametrize(
    ("game", "count"),
    [
        (Game.NUMBERS3, 3),
        (Game.NUMBERS4, 4),
        (Game.MINILOTO, 5),
        (Game.LOTO6, 6),
        (Game.LOTO7, 7),
    ],
)
def test_five_game_structural_geometry(game: Game, count: int) -> None:
    assert position_count_for_game(game) == count


@pytest.mark.parametrize(
    "timeline_mode",
    [TimelineMode.DRAW_SEQUENCE, TimelineMode.CALENDAR_TIME],
)
def test_compile_history_transposes_positions_and_hashes_mapping(
    timeline_mode: TimelineMode,
) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = tuple(
        HistoryRow(
            timestamp=start + timedelta(days=index * 7),
            values=(float(index), float(index + 1), float(index + 2)),
        )
        for index in range(3)
    )
    compiled = compile_history(Game.NUMBERS3, rows, 3, timeline_mode)
    assert compiled.input_shape == (3, 3)
    assert compiled.native_input[0] == (0.0, 1.0, 2.0)
    assert len(compiled.calendar_mapping_sha256) == 64


def test_duplicate_or_out_of_order_timestamp_is_rejected() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    rows = (
        HistoryRow(timestamp=timestamp, values=(1.0, 2.0, 3.0)),
        HistoryRow(timestamp=timestamp, values=(2.0, 3.0, 4.0)),
    )
    with pytest.raises(ValueError, match="strictly increasing"):
        compile_history(Game.NUMBERS3, rows, 2, TimelineMode.DRAW_SEQUENCE)

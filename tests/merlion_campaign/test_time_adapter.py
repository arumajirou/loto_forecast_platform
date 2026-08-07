from __future__ import annotations

from datetime import datetime, timezone

import pytest

from loto.merlion_campaign.protocol import SeriesPayload, TimeSemantics
from loto.merlion_campaign.time_adapter import compile_series


def test_draw_sequence_compiles_deterministically() -> None:
    payload = SeriesPayload(
        name="N1",
        values=[2.0, 3.0, 4.0],
        draw_numbers=[10, 11, 12],
    )
    first = compile_series(payload, TimeSemantics.DRAW_SEQUENCE)
    second = compile_series(payload, TimeSemantics.DRAW_SEQUENCE)
    assert first.frame.shape == (3, 1)
    assert first.mapping_sha256 == second.mapping_sha256
    assert first.mapping[0]["draw_number"] == 10


def test_draw_sequence_rejects_gaps() -> None:
    payload = SeriesPayload(
        name="N1",
        values=[2.0, 3.0, 4.0],
        draw_numbers=[10, 12, 13],
    )
    with pytest.raises(ValueError, match="gap-free"):
        compile_series(payload, TimeSemantics.DRAW_SEQUENCE)


def test_calendar_time_preserves_real_timestamps() -> None:
    payload = SeriesPayload(
        name="N1",
        values=[2.0, 3.0, 4.0],
        timestamps=[
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 8, tzinfo=timezone.utc),
            datetime(2026, 1, 15, tzinfo=timezone.utc),
        ],
    )
    compiled = compile_series(payload, TimeSemantics.CALENDAR_TIME)
    assert compiled.frame.index[1].day == 8


def test_calendar_time_rejects_naive_timestamps() -> None:
    payload = SeriesPayload(
        name="N1",
        values=[2.0, 3.0, 4.0],
        timestamps=[
            datetime(2026, 1, 1),
            datetime(2026, 1, 8),
            datetime(2026, 1, 15),
        ],
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        compile_series(payload, TimeSemantics.CALENDAR_TIME)

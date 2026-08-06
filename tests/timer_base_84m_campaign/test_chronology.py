from __future__ import annotations

from datetime import date, timedelta

import pytest

from loto.timer_base_84m_campaign.chronology import ChronologyError, TimeAxis, validate_chronology
from loto.timer_base_84m_campaign.geometry import Game


def test_duplicate_chronology_rejected() -> None:
    with pytest.raises(ChronologyError, match="duplicate"):
        validate_chronology(
            game=Game.NUMBERS3,
            time_axis=TimeAxis.DRAW_SEQUENCE,
            draw_numbers=(1, 1),
            dates=(date(2026, 1, 1), date(2026, 1, 2)),
            cutoff_draw_no=2,
            cutoff_date=date(2026, 1, 2),
            actuals_used=False,
        )


def test_reverse_chronology_rejected() -> None:
    with pytest.raises(ChronologyError, match="strictly increasing"):
        validate_chronology(
            game=Game.NUMBERS3,
            time_axis=TimeAxis.DRAW_SEQUENCE,
            draw_numbers=(2, 1),
            dates=(date(2026, 1, 1), date(2026, 1, 2)),
            cutoff_draw_no=2,
            cutoff_date=date(2026, 1, 2),
            actuals_used=False,
        )


def test_future_actual_rejected() -> None:
    with pytest.raises(ChronologyError, match="future actuals"):
        validate_chronology(
            game=Game.NUMBERS3,
            time_axis=TimeAxis.DRAW_SEQUENCE,
            draw_numbers=(1, 2),
            dates=(date(2026, 1, 1), date(2026, 1, 2)),
            cutoff_draw_no=2,
            cutoff_date=date(2026, 1, 2),
            actuals_used=True,
        )


def test_draw_sequence_gap_rejected() -> None:
    with pytest.raises(ChronologyError, match="gap-free"):
        validate_chronology(
            game=Game.NUMBERS3,
            time_axis=TimeAxis.DRAW_SEQUENCE,
            draw_numbers=(1, 3),
            dates=(date(2026, 1, 1), date(2026, 1, 2)),
            cutoff_draw_no=3,
            cutoff_date=date(2026, 1, 2),
            actuals_used=False,
        )


def test_calendar_schedule_gap_rejected() -> None:
    monday = date(2026, 1, 5)
    thursday = monday + timedelta(days=3)
    next_monday = monday + timedelta(days=7)
    with pytest.raises(ChronologyError, match="weekday schedule"):
        validate_chronology(
            game=Game.LOTO6,
            time_axis=TimeAxis.CALENDAR_TIME,
            draw_numbers=(1, 2),
            dates=(monday, next_monday),
            cutoff_draw_no=2,
            cutoff_date=next_monday,
            actuals_used=False,
        )
    assert thursday.weekday() == 3

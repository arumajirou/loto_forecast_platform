from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta

from loto.timer_base_84m_campaign._compat import StrEnum
from loto.timer_base_84m_campaign.geometry import Game, geometry_for


class TimeAxis(StrEnum):
    DRAW_SEQUENCE = "draw_sequence"
    CALENDAR_TIME = "calendar_time"


class ChronologyError(ValueError):
    pass


def _mapping_sha256(
    *, game: Game, time_axis: TimeAxis, draw_numbers: tuple[int, ...], dates: tuple[date, ...]
) -> str:
    payload = {
        "game": game.value,
        "time_axis": time_axis.value,
        "draw_numbers": list(draw_numbers),
        "dates": [value.isoformat() for value in dates],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _scheduled_dates(start: date, end: date, weekdays: tuple[int, ...]) -> tuple[date, ...]:
    values: list[date] = []
    current = start
    while current <= end:
        if current.weekday() in weekdays:
            values.append(current)
        current += timedelta(days=1)
    return tuple(values)


def validate_chronology(
    *,
    game: Game,
    time_axis: TimeAxis,
    draw_numbers: tuple[int, ...],
    dates: tuple[date, ...],
    cutoff_draw_no: int,
    cutoff_date: date,
    actuals_used: bool,
) -> str:
    if actuals_used:
        raise ChronologyError("future actuals are forbidden")
    if len(draw_numbers) != len(dates) or not draw_numbers:
        raise ChronologyError("draw number and date evidence must be non-empty and aligned")
    if len(set(draw_numbers)) != len(draw_numbers) or len(set(dates)) != len(dates):
        raise ChronologyError("duplicate chronology evidence")
    if any(right <= left for left, right in zip(draw_numbers, draw_numbers[1:], strict=False)):
        raise ChronologyError("draw numbers must be strictly increasing")
    if any(right <= left for left, right in zip(dates, dates[1:], strict=False)):
        raise ChronologyError("dates must be strictly increasing")
    if draw_numbers[-1] > cutoff_draw_no or dates[-1] > cutoff_date:
        raise ChronologyError("chronology extends beyond prediction cutoff")
    expected_draw_numbers = tuple(range(draw_numbers[0], draw_numbers[-1] + 1))
    if draw_numbers != expected_draw_numbers:
        raise ChronologyError("draw number evidence must be gap-free")
    if time_axis is TimeAxis.CALENDAR_TIME:
        weekdays = geometry_for(game).draw_weekdays
        expected_dates = _scheduled_dates(dates[0], dates[-1], weekdays)
        if dates != expected_dates:
            raise ChronologyError(
                "calendar_time evidence must match the deterministic weekday schedule; "
                "holiday and year-end exceptions require a reviewed schedule override"
            )
    return _mapping_sha256(
        game=game,
        time_axis=time_axis,
        draw_numbers=draw_numbers,
        dates=dates,
    )

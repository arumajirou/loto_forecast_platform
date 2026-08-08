from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TimeAxis:
    start: str
    frequency: str
    target: np.ndarray
    mapping: list[dict[str, str | int]]
    mapping_sha256: str
    frequency_policy: str
    missing_period_policy: str


def _mapping_sha256(mapping: list[dict[str, str | int]]) -> str:
    encoded = json.dumps(
        mapping,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_draw_sequence_axis(
    target: np.ndarray,
    draw_numbers: Iterable[int] | None = None,
) -> TimeAxis:
    if target.ndim != 2 or target.shape[1] < 1:
        raise ValueError("target must have shape [position, time]")
    length = target.shape[1]
    draws = list(draw_numbers) if draw_numbers is not None else list(range(1, length + 1))
    if len(draws) != length:
        raise ValueError("draw_numbers must match target length")
    if any(not isinstance(draw, int) for draw in draws):
        raise ValueError("draw_numbers must be integers")
    expected_draws = list(range(draws[0], draws[0] + length))
    if draws != expected_draws:
        raise ValueError("draw_numbers must be unique, increasing, and gap-free")
    start = datetime(2000, 1, 1, tzinfo=UTC)
    mapping = [
        {
            "draw_no": draw,
            "timestamp": (start + timedelta(days=index)).isoformat(),
        }
        for index, draw in enumerate(draws)
    ]
    return TimeAxis(
        start=str(mapping[0]["timestamp"]),
        frequency="D",
        target=target.copy(),
        mapping=mapping,
        mapping_sha256=_mapping_sha256(mapping),
        frequency_policy="one_period_per_draw",
        missing_period_policy="forbid_missing_draw_sequence",
    )


def build_calendar_time_axis(target: np.ndarray, timestamps: Iterable[datetime]) -> TimeAxis:
    values = list(timestamps)
    if target.ndim != 2 or len(values) != target.shape[1]:
        raise ValueError("timestamps must match target length")
    normalized = pd.DatetimeIndex(pd.to_datetime(values, utc=True))
    if normalized.has_duplicates or not normalized.is_monotonic_increasing:
        raise ValueError("calendar timestamps must be unique and increasing")
    if any(timestamp != timestamp.normalize() for timestamp in normalized):
        raise ValueError("calendar_time currently requires date-level timestamps")
    complete = pd.date_range(normalized[0], normalized[-1], freq="D", tz="UTC")
    expanded = np.full((target.shape[0], len(complete)), np.nan, dtype=np.float32)
    locations = complete.get_indexer(normalized)
    expanded[:, locations] = target
    observed = set(normalized)
    mapping = [
        {
            "calendar_date": timestamp.isoformat(),
            "observed_draw": timestamp in observed,
        }
        for timestamp in complete
    ]
    return TimeAxis(
        start=complete[0].isoformat(),
        frequency="D",
        target=expanded,
        mapping=mapping,
        mapping_sha256=_mapping_sha256(mapping),
        frequency_policy="daily_calendar_grid",
        missing_period_policy="preserve_as_nan",
    )

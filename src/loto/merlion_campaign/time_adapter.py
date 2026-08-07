from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from loto.merlion_campaign.protocol import SeriesPayload, TimeSemantics


@dataclass(frozen=True)
class CompiledSeries:
    frame: pd.DataFrame
    mapping: list[dict[str, object]]
    mapping_sha256: str


def _mapping_hash(mapping: list[dict[str, object]]) -> str:
    payload = json.dumps(
        mapping,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compile_series(payload: SeriesPayload, semantics: TimeSemantics) -> CompiledSeries:
    values = np.asarray(payload.values, dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("series values must all be finite")

    mapping: list[dict[str, object]] = []
    if semantics is TimeSemantics.DRAW_SEQUENCE:
        if payload.draw_numbers is None or payload.timestamps is not None:
            raise ValueError("draw_sequence requires draw_numbers and forbids timestamps")
        draws = payload.draw_numbers
        if any(isinstance(value, bool) for value in draws):
            raise ValueError("draw numbers must be integers, not booleans")
        if draws != sorted(draws) or len(set(draws)) != len(draws):
            raise ValueError("draw numbers must be strictly increasing and unique")
        if any(right - left != 1 for left, right in zip(draws, draws[1:])):
            raise ValueError("draw numbers must be gap-free")
        base = datetime(2000, 1, 1, tzinfo=timezone.utc)
        index = [base + timedelta(days=offset) for offset in range(len(draws))]
        mapping = [
            {
                "draw_number": draw,
                "synthetic_timestamp": timestamp.isoformat(),
            }
            for draw, timestamp in zip(draws, index, strict=True)
        ]
    else:
        if payload.timestamps is None or payload.draw_numbers is not None:
            raise ValueError("calendar_time requires timestamps and forbids draw_numbers")
        if any(
            timestamp.tzinfo is None or timestamp.utcoffset() is None
            for timestamp in payload.timestamps
        ):
            raise ValueError("calendar timestamps must be timezone-aware")
        index = [timestamp.astimezone(timezone.utc) for timestamp in payload.timestamps]
        if index != sorted(index) or len(set(index)) != len(index):
            raise ValueError("timestamps must be strictly increasing and unique")
        mapping = [
            {"calendar_timestamp": timestamp.isoformat()}
            for timestamp in index
        ]

    frame = pd.DataFrame({payload.name: values}, index=pd.DatetimeIndex(index))
    frame.index.name = "timestamp"
    return CompiledSeries(
        frame=frame,
        mapping=mapping,
        mapping_sha256=_mapping_hash(mapping),
    )

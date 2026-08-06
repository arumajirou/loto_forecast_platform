from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime

from loto.adapters.timer_s1.contracts import (
    POSITION_COUNTS,
    Game,
    HistoryRow,
    TimelineMode,
)


@dataclass(frozen=True)
class CompiledGeometry:
    game: Game
    position_count: int
    native_input: tuple[tuple[float, ...], ...]
    input_shape: tuple[int, int]
    first_timestamp: datetime
    last_timestamp: datetime
    calendar_mapping_sha256: str


def position_count_for_game(game: Game) -> int:
    return POSITION_COUNTS[game]


def compile_history(
    game: Game,
    rows: tuple[HistoryRow, ...],
    context_length: int,
    timeline_mode: TimelineMode,
) -> CompiledGeometry:
    if len(rows) < context_length:
        raise ValueError("history does not cover requested context_length")
    selected = rows[-context_length:]
    timestamps = [row.timestamp for row in selected]
    if any(left >= right for left, right in zip(timestamps, timestamps[1:], strict=False)):
        raise ValueError("history timestamps must be strictly increasing and unique")
    position_count = position_count_for_game(game)
    for index, row in enumerate(selected):
        if len(row.values) != position_count:
            raise ValueError(
                f"history row {index} has {len(row.values)} values; expected {position_count}"
            )
        if row.future_actual:
            raise ValueError("future actuals are forbidden")
        if any(not math.isfinite(value) for value in row.values):
            raise ValueError("history contains non-finite values")

    mapping = [
        {
            "draw_index": index + 1,
            "timestamp": timestamp.isoformat(),
            "timeline_mode": timeline_mode.value,
        }
        for index, timestamp in enumerate(timestamps)
    ]
    mapping_bytes = json.dumps(
        mapping,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    native_input = tuple(
        tuple(float(row.values[position]) for row in selected)
        for position in range(position_count)
    )
    return CompiledGeometry(
        game=game,
        position_count=position_count,
        native_input=native_input,
        input_shape=(position_count, context_length),
        first_timestamp=timestamps[0],
        last_timestamp=timestamps[-1],
        calendar_mapping_sha256=hashlib.sha256(mapping_bytes).hexdigest(),
    )

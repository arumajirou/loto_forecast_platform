from __future__ import annotations

import re
from collections.abc import Iterable

import pandas as pd

from loto.adapters.timesfm25.contracts import GameGeometry

_NATURAL_SUFFIX = re.compile(r"^(.*?)(\d+)$")


def natural_series_sort(values: Iterable[str]) -> list[str]:
    def key(value: str) -> tuple[str, int, str]:
        match = _NATURAL_SUFFIX.match(value)
        if match is None:
            return (value, -1, value)
        return (match.group(1), int(match.group(2)), value)

    return sorted(values, key=key)


def infer_position_columns(history: pd.DataFrame) -> list[str]:
    columns = [str(column) for column in history.columns if re.fullmatch(r"n\d+", str(column))]
    if not columns:
        raise ValueError("no position columns matching n<integer> were found")
    return natural_series_sort(columns)


def validate_geometry_columns(geometry: GameGeometry, columns: list[str]) -> None:
    if len(columns) != geometry.position_count:
        raise ValueError(
            f"position count mismatch: geometry={geometry.position_count}, columns={len(columns)}"
        )
    if len(set(columns)) != len(columns):
        raise ValueError("position columns must be unique")

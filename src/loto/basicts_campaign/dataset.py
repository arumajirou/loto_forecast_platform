from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class GameGeometry:
    """Explicit game and position identity contract for BasicTS arrays."""

    game_id: str
    position_columns: tuple[str, ...]
    minimum_value: int
    maximum_value: int

    def __post_init__(self) -> None:
        if not self.game_id.strip():
            raise ValueError("game_id must be non-empty")
        if not self.position_columns or len(set(self.position_columns)) != len(
            self.position_columns
        ):
            raise ValueError("position_columns must be non-empty and unique")
        if self.minimum_value > self.maximum_value:
            raise ValueError("minimum_value must not exceed maximum_value")


@dataclass(frozen=True)
class WindowedDataset:
    """Immutable supervised windows plus exact sample identity."""

    inputs: np.ndarray
    targets: np.ndarray
    sample_identity: tuple[dict[str, Any], ...]


def compile_wide_rows(
    rows: list[dict[str, Any]],
    geometry: GameGeometry,
) -> tuple[np.ndarray, tuple[dict[str, Any], ...]]:
    """Compile already-ordered draw rows without sorting or repairing them."""

    if not rows:
        raise ValueError("rows must be non-empty")
    draw_numbers = [row.get("draw_no") for row in rows]
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in draw_numbers):
        raise ValueError("draw_no must contain integers")
    if len(set(draw_numbers)) != len(draw_numbers):
        raise ValueError("draw_no must be unique")
    if draw_numbers != sorted(draw_numbers):
        raise ValueError("rows must already be ordered by draw_no")
    if any(right - left != 1 for left, right in zip(draw_numbers, draw_numbers[1:])):
        raise ValueError("draw_no must be gap-free")

    values: list[list[float]] = []
    identity: list[dict[str, Any]] = []
    for row in rows:
        current: list[float] = []
        for position in geometry.position_columns:
            if position not in row:
                raise ValueError(f"missing position column: {position}")
            value = float(row[position])
            if not np.isfinite(value):
                raise ValueError(f"non-finite value in position column: {position}")
            if not geometry.minimum_value <= value <= geometry.maximum_value:
                raise ValueError(f"out-of-range value in position column: {position}")
            current.append(value)
        values.append(current)
        identity.append(
            {
                "game_id": geometry.game_id,
                "draw_no": row["draw_no"],
                "draw_date": row.get("draw_date"),
                "position_columns": list(geometry.position_columns),
            }
        )
    return np.asarray(values, dtype=np.float32), tuple(identity)


def build_windows(
    values: np.ndarray,
    identity: tuple[dict[str, Any], ...],
    *,
    input_len: int,
    output_len: int,
) -> WindowedDataset:
    """Create chronological windows while retaining target draw identities."""

    matrix = np.asarray(values, dtype=np.float32)
    if matrix.ndim != 2 or not np.isfinite(matrix).all():
        raise ValueError("values must be a finite two-dimensional matrix")
    if len(identity) != len(matrix):
        raise ValueError("identity length must match values")
    if input_len <= 0 or output_len <= 0:
        raise ValueError("input_len and output_len must be positive")
    sample_count = len(matrix) - input_len - output_len + 1
    if sample_count <= 0:
        raise ValueError("insufficient rows for requested window geometry")

    inputs: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    sample_identity: list[dict[str, Any]] = []
    for start in range(sample_count):
        target_start = start + input_len
        target_stop = target_start + output_len
        inputs.append(matrix[start:target_start].copy())
        targets.append(matrix[target_start:target_stop].copy())
        sample_identity.append(
            {
                "input_first_draw_no": identity[start]["draw_no"],
                "input_last_draw_no": identity[target_start - 1]["draw_no"],
                "target_draw_nos": [
                    identity[index]["draw_no"] for index in range(target_start, target_stop)
                ],
                "game_id": identity[start]["game_id"],
                "position_columns": identity[start]["position_columns"],
            }
        )
    return WindowedDataset(
        inputs=np.stack(inputs),
        targets=np.stack(targets),
        sample_identity=tuple(sample_identity),
    )

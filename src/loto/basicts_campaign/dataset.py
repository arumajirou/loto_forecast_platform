from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .contracts import DatasetPayload
from .provenance import atomic_write_json, canonical_json_bytes, sha256_bytes


@dataclass(frozen=True, init=False)
class GameGeometry:
    """Game geometry supporting both current and pre-conflict BasicTS call contracts."""

    game: str
    positions: int
    minimum: int
    maximum: int
    _position_columns: tuple[str, ...] = field(repr=False, compare=False)

    def __init__(
        self,
        game: str | None = None,
        positions: int | None = None,
        minimum: int | None = None,
        maximum: int | None = None,
        *,
        game_id: str | None = None,
        position_columns: tuple[str, ...] | None = None,
        minimum_value: int | None = None,
        maximum_value: int | None = None,
    ) -> None:
        legacy = any(
            value is not None for value in (game_id, position_columns, minimum_value, maximum_value)
        )
        current = any(value is not None for value in (game, positions, minimum, maximum))
        if legacy and current:
            raise ValueError("current and legacy GameGeometry arguments must not be mixed")

        if legacy:
            if (
                game_id is None
                or position_columns is None
                or minimum_value is None
                or maximum_value is None
            ):
                raise ValueError("legacy GameGeometry arguments must be complete")
            columns = tuple(position_columns)
            if not game_id.strip():
                raise ValueError("game_id must be non-empty")
            if not columns or len(set(columns)) != len(columns):
                raise ValueError("position_columns must be non-empty and unique")
            resolved_game = game_id
            resolved_positions = len(columns)
            resolved_minimum = minimum_value
            resolved_maximum = maximum_value
        else:
            if game is None or positions is None or minimum is None or maximum is None:
                raise ValueError("current GameGeometry arguments must be complete")
            if not game.strip() or positions < 1:
                raise ValueError("game must be non-empty and positions must be positive")
            resolved_game = game
            resolved_positions = positions
            resolved_minimum = minimum
            resolved_maximum = maximum
            columns = tuple(f"N{index}" for index in range(1, positions + 1))

        if resolved_minimum > resolved_maximum:
            raise ValueError("minimum must not exceed maximum")
        object.__setattr__(self, "game", resolved_game)
        object.__setattr__(self, "positions", resolved_positions)
        object.__setattr__(self, "minimum", resolved_minimum)
        object.__setattr__(self, "maximum", resolved_maximum)
        object.__setattr__(self, "_position_columns", columns)

    @property
    def game_id(self) -> str:
        return self.game

    @property
    def position_columns(self) -> tuple[str, ...]:
        return self._position_columns

    @property
    def minimum_value(self) -> int:
        return self.minimum

    @property
    def maximum_value(self) -> int:
        return self.maximum


GEOMETRIES: dict[str, GameGeometry] = {
    "numbers3": GameGeometry("numbers3", 3, 0, 9),
    "numbers4": GameGeometry("numbers4", 4, 0, 9),
    "miniloto": GameGeometry("miniloto", 5, 1, 31),
    "loto6": GameGeometry("loto6", 6, 1, 43),
    "loto7": GameGeometry("loto7", 7, 1, 37),
}


@dataclass(frozen=True)
class ChronologicalSplit:
    train: np.ndarray
    validation: np.ndarray
    holdout: np.ndarray
    train_draw_no: tuple[int, ...]
    validation_draw_no: tuple[int, ...]
    holdout_draw_no: tuple[int, ...]


@dataclass(frozen=True)
class WindowedDataset:
    """Immutable supervised windows plus exact sample identity."""

    inputs: np.ndarray
    targets: np.ndarray
    sample_identity: tuple[dict[str, Any], ...]


def validate_dataset(payload: DatasetPayload) -> tuple[np.ndarray, tuple[int, ...], GameGeometry]:
    geometry = GEOMETRIES[payload.game]
    draw_numbers = tuple(row.draw_no for row in payload.rows)
    if tuple(sorted(draw_numbers)) != draw_numbers:
        raise ValueError("draw_no must already be strictly chronological")
    if len(set(draw_numbers)) != len(draw_numbers):
        raise ValueError("draw_no values must be unique")
    if any(right - left != 1 for left, right in zip(draw_numbers, draw_numbers[1:], strict=False)):
        raise ValueError("draw_no values must be gap-free")

    values = np.asarray([row.values for row in payload.rows], dtype=np.int64)
    if values.ndim != 2 or values.shape[1] != geometry.positions:
        raise ValueError(
            f"{payload.game} requires {geometry.positions} positions, got shape={values.shape}"
        )
    if np.any(values < geometry.minimum) or np.any(values > geometry.maximum):
        raise ValueError(
            f"values must be in [{geometry.minimum}, {geometry.maximum}] for {payload.game}"
        )
    return values, draw_numbers, geometry


def split_chronologically(payload: DatasetPayload) -> ChronologicalSplit:
    values, draw_numbers, _ = validate_dataset(payload)
    holdout_start = len(values) - payload.holdout_size
    validation_start = holdout_start - payload.validation_size
    train = values[:validation_start].copy()
    validation = values[validation_start:holdout_start].copy()
    holdout = values[holdout_start:].copy()
    return ChronologicalSplit(
        train=train,
        validation=validation,
        holdout=holdout,
        train_draw_no=draw_numbers[:validation_start],
        validation_draw_no=draw_numbers[validation_start:holdout_start],
        holdout_draw_no=draw_numbers[holdout_start:],
    )


def compile_wide_rows(
    rows: list[dict[str, Any]],
    geometry: GameGeometry,
) -> tuple[np.ndarray, tuple[dict[str, Any], ...]]:
    """Compile already-ordered draw rows while preserving legacy sample identity."""

    if not rows:
        raise ValueError("rows must be non-empty")
    draw_numbers = [row.get("draw_no") for row in rows]
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in draw_numbers):
        raise ValueError("draw_no must contain integers")
    if len(set(draw_numbers)) != len(draw_numbers):
        raise ValueError("draw_no must be unique")
    if draw_numbers != sorted(draw_numbers):
        raise ValueError("rows must already be ordered by draw_no")
    if any(right - left != 1 for left, right in zip(draw_numbers, draw_numbers[1:], strict=False)):
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
            if not geometry.minimum <= value <= geometry.maximum:
                raise ValueError(f"out-of-range value in position column: {position}")
            current.append(value)
        values.append(current)
        identity.append(
            {
                "game_id": geometry.game,
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


def _as_basicts_array(values: np.ndarray) -> np.ndarray:
    return values.astype(np.float32, copy=True)[:, :, np.newaxis]


def compile_basic_ts_dataset(payload: DatasetPayload, output_dir: Path) -> dict[str, Any]:
    split = split_chronologically(payload)
    output_dir.mkdir(parents=True, exist_ok=True)
    arrays = {
        "train": _as_basicts_array(split.train),
        "val": _as_basicts_array(split.validation),
        # This is a development-only validation lane. Formal Holdout is not exposed to BasicTS.
        "test": _as_basicts_array(split.validation),
    }
    artifacts: list[str] = []
    for name, values in arrays.items():
        path = output_dir / f"{name}_data.npy"
        np.save(path, values, allow_pickle=False)
        artifacts.append(path.name)

    identity = {
        "game": payload.game,
        "train_draw_no": list(split.train_draw_no),
        "validation_draw_no": list(split.validation_draw_no),
        "holdout_draw_no_sha256": sha256_bytes(canonical_json_bytes(split.holdout_draw_no)),
        "formal_holdout_materialized": False,
        "basic_ts_test_alias": "validation",
    }
    identity_path = output_dir / "identity.json"
    atomic_write_json(identity_path, identity)
    artifacts.append(identity_path.name)

    raw_hash = sha256_bytes(canonical_json_bytes(payload.model_dump(mode="json")))
    return {
        "raw_payload_sha256": raw_hash,
        "train_shape": list(arrays["train"].shape),
        "validation_shape": list(arrays["val"].shape),
        "formal_holdout_rows": len(split.holdout),
        "formal_holdout_materialized": False,
        "scaler_fit_scope": "train_only",
        "artifacts": artifacts,
    }

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .contracts import DatasetPayload
from .provenance import atomic_write_json, canonical_json_bytes, sha256_bytes


@dataclass(frozen=True)
class GameGeometry:
    game: str
    positions: int
    minimum: int
    maximum: int


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

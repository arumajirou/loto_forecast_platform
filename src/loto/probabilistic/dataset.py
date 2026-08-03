from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.game.geometry import GameGeometry, geometry_for
from loto.probabilistic.config import stable_hash
from loto.probabilistic.contracts import TargetMode


@dataclass(frozen=True)
class DatasetBundle:
    game: str
    geometry: GameGeometry
    frame: pd.DataFrame
    values: np.ndarray
    draw_ids: tuple[str, ...]
    data_version: str
    feature_set_hash: str
    candidate_indicator: np.ndarray | None = None
    set_members: tuple[tuple[int, ...], ...] | None = None
    set_cardinality: int | None = None
    position_tokens: np.ndarray | None = None
    joint_tokens: tuple[str, ...] | None = None
    draw_order: np.ndarray | None = None
    draw_order_verified: bool = False

    @property
    def rows(self) -> int:
        return int(self.values.shape[0])


def _resolve_columns(frame: pd.DataFrame, geometry: GameGeometry) -> list[str]:
    candidates = [geometry.column_names()]
    if geometry.family == "select":
        candidates.extend(
            [
                [f"N{i}" for i in range(1, geometry.positions + 1)],
                [f"number{i}" for i in range(1, geometry.positions + 1)],
            ]
        )
    else:
        candidates.extend(
            [
                [f"D{i}" for i in range(1, geometry.positions + 1)],
                [f"digit{i}" for i in range(1, geometry.positions + 1)],
                [f"n{i}" for i in range(1, geometry.positions + 1)],
            ]
        )
    lower_map = {str(col).lower(): str(col) for col in frame.columns}
    for group in candidates:
        resolved = [lower_map.get(col.lower()) for col in group]
        if all(resolved):
            return [str(x) for x in resolved]
    numeric = [str(col) for col in frame.select_dtypes(include=["number"]).columns]
    ignored = {"draw_no", "draw", "round", "id", "year", "month", "day"}
    numeric = [col for col in numeric if col.lower() not in ignored]
    if len(numeric) >= geometry.positions:
        return numeric[: geometry.positions]
    raise ValueError(
        f"could not resolve {geometry.positions} target columns for {geometry.key}; "
        f"available={list(frame.columns)}"
    )


def _resolve_named_columns(frame: pd.DataFrame, names: Sequence[str]) -> list[str]:
    lower_map = {str(col).lower(): str(col) for col in frame.columns}
    resolved = [lower_map.get(str(name).lower()) for name in names]
    if not all(resolved):
        missing = [name for name, value in zip(names, resolved, strict=True) if value is None]
        raise ValueError(f"draw order columns are missing: {missing}")
    return [str(value) for value in resolved]


def _candidate_indicator(values: np.ndarray, geometry: GameGeometry) -> np.ndarray:
    indicator = np.zeros((len(values), geometry.universe_size), dtype=np.int8)
    zero_based = values - geometry.value_min
    for row_index, row in enumerate(zero_based):
        indicator[row_index, row] = 1
    return indicator


def _validated_draw_order(
    frame: pd.DataFrame,
    *,
    columns: Sequence[str],
    values: np.ndarray,
    geometry: GameGeometry,
) -> np.ndarray:
    if geometry.family != "select":
        raise ValueError("draw order is only valid for select-family games")
    if len(columns) != geometry.positions:
        raise ValueError(
            f"draw order requires {geometry.positions} columns, got {len(columns)}"
        )
    resolved = _resolve_named_columns(frame, columns)
    ordered = frame[resolved].to_numpy(dtype=int)
    for index, (ordered_row, sorted_row) in enumerate(
        zip(ordered, values, strict=True)
    ):
        if len(set(ordered_row.tolist())) != geometry.positions:
            raise ValueError(f"draw order row {index} contains duplicates")
        if any(value not in geometry.values for value in ordered_row):
            raise ValueError(f"draw order row {index} contains an out-of-range value")
        if set(ordered_row.tolist()) != set(sorted_row.tolist()):
            raise ValueError(f"draw order row {index} does not match the legal result set")
    return ordered


def load_dataset(
    path: str | Path,
    game: str,
    *,
    draw_order_columns: Sequence[str] | None = None,
    draw_order_verified: bool = False,
) -> DatasetBundle:
    source = Path(path)
    if source.suffix.lower() in {".parquet", ".pq"}:
        frame = pd.read_parquet(source)
    else:
        frame = pd.read_csv(source)
    return bundle_from_frame(
        frame,
        game=game,
        data_version=f"{source.name}-{source.stat().st_size}",
        draw_order_columns=draw_order_columns,
        draw_order_verified=draw_order_verified,
    )


def bundle_from_frame(
    frame: pd.DataFrame,
    *,
    game: str,
    data_version: str | None = None,
    draw_order_columns: Sequence[str] | None = None,
    draw_order_verified: bool = False,
) -> DatasetBundle:
    geometry = geometry_for(game)
    columns = _resolve_columns(frame, geometry)
    target = frame[columns].copy()
    if target.isna().any().any():
        raise ValueError("target columns contain nulls")
    values = target.to_numpy(dtype=int)
    for row in values:
        geometry.validate_outcome(row.tolist())

    if draw_order_verified and draw_order_columns is None:
        raise ValueError("draw_order_verified=true requires explicit draw_order_columns")
    draw_order = None
    if draw_order_columns is not None:
        draw_order = _validated_draw_order(
            frame,
            columns=draw_order_columns,
            values=values,
            geometry=geometry,
        )

    draw_col = next(
        (col for col in frame.columns if str(col).lower() in {"draw_no", "draw", "round", "id"}),
        None,
    )
    draw_ids = (
        tuple(frame[draw_col].astype(str).tolist())
        if draw_col is not None
        else tuple(str(i + 1) for i in range(len(frame)))
    )
    version = data_version or f"{game}-frame-{len(frame)}-{stable_hash(values.tolist())[:12]}"
    feature_set_hash = stable_hash({"columns": columns, "rows": len(frame), "game": game})
    normalized = frame.copy()
    normalized = normalized.rename(
        columns=dict(zip(columns, geometry.column_names(), strict=False))
    )

    candidate_indicator = None
    set_members = None
    set_cardinality = None
    position_tokens = None
    joint_tokens = None
    if geometry.family == "select":
        candidate_indicator = _candidate_indicator(values, geometry)
        set_members = tuple(tuple(int(item) for item in row) for row in values)
        set_cardinality = geometry.positions
    else:
        position_tokens = values.copy()
        joint_tokens = tuple("".join(str(int(item)) for item in row) for row in values)

    return DatasetBundle(
        game=game,
        geometry=geometry,
        frame=normalized,
        values=values,
        draw_ids=draw_ids,
        data_version=version,
        feature_set_hash=feature_set_hash,
        candidate_indicator=candidate_indicator,
        set_members=set_members,
        set_cardinality=set_cardinality,
        position_tokens=position_tokens,
        joint_tokens=joint_tokens,
        draw_order=draw_order,
        draw_order_verified=bool(draw_order is not None and draw_order_verified),
    )


def synthetic_dataset(game: str, *, rows: int = 240, seed: int = 42) -> DatasetBundle:
    geometry = geometry_for(game)
    rng = np.random.default_rng(seed)
    output: list[dict[str, Any]] = []
    # A weak, non-stationary signal is deliberate: smoke tests must exercise dynamic models
    # without pretending that the signal represents a real lottery mechanism.
    phase = rng.uniform(0.0, 2 * np.pi, size=geometry.positions)
    for index in range(rows):
        if geometry.family == "digits":
            vals = []
            for position in range(geometry.positions):
                base = int(round(4.5 + 1.25 * np.sin(index / 19.0 + phase[position])))
                value = int(np.clip(base + rng.integers(-3, 4), 0, 9))
                vals.append(value)
        else:
            scores = rng.normal(0.0, 1.0, size=geometry.universe_size)
            seasonal = np.sin(index / 23.0 + np.arange(geometry.universe_size) / 7.0)
            scores += 0.12 * seasonal
            chosen = np.argpartition(scores, -geometry.positions)[-geometry.positions :]
            vals = sorted((chosen + geometry.value_min).tolist())
        output.append(
            {"draw_no": index + 1, **dict(zip(geometry.column_names(), vals, strict=False))}
        )
    return bundle_from_frame(
        pd.DataFrame(output), game=game, data_version=f"{game}-synthetic-{rows}-seed{seed}"
    )


def task_arrays(bundle: DatasetBundle, target_mode: str) -> tuple[np.ndarray, int]:
    geometry = bundle.geometry
    zero_based = bundle.values - geometry.value_min
    if target_mode in {
        "digit_categorical",
        "digit_ordinal",
        "select_position_categorical",
        "select_position_ordinal",
        "select_position_inclusion",
        TargetMode.CATEGORICAL_CONTEXT,
        TargetMode.DYNAMIC_MULTINOMIAL,
        TargetMode.JOINT_DISCRETE_COPULA,
        TargetMode.ONLINE_CHANGEPOINT,
    }:
        if target_mode in {
            TargetMode.CATEGORICAL_CONTEXT,
            TargetMode.JOINT_DISCRETE_COPULA,
        } and geometry.family != "digits":
            raise ValueError(f"{target_mode} requires a digits-family game")
        return zero_based, geometry.universe_size
    if target_mode == TargetMode.FIXED_CARDINALITY_SUBSET:
        if geometry.family != "select" or bundle.candidate_indicator is None:
            raise ValueError("fixed_cardinality_subset requires a select-family game")
        return bundle.candidate_indicator.copy(), geometry.universe_size
    if target_mode == TargetMode.ORDERED_WITHOUT_REPLACEMENT:
        if not bundle.draw_order_verified or bundle.draw_order is None:
            raise ValueError("ordered_without_replacement requires verified draw order")
        return bundle.draw_order - geometry.value_min, geometry.universe_size
    if target_mode in {"select_candidate_inclusion", "window_count"}:
        incidence = np.zeros((bundle.rows, geometry.universe_size), dtype=int)
        if geometry.family == "select":
            for index, row in enumerate(zero_based):
                incidence[index, row] = 1
        else:
            for index, row in enumerate(zero_based):
                incidence[index] = np.bincount(row, minlength=geometry.universe_size)
        return incidence, geometry.universe_size
    if target_mode in {"calibration", "ensemble", "decision"}:
        return zero_based, geometry.universe_size
    raise ValueError(f"unsupported target_mode: {target_mode}")

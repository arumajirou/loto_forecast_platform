from __future__ import annotations

import numpy as np
import pandas as pd

from .contracts import GameGeometry, TimeAxisMode

_REQUIRED_LONG_COLUMNS = ("unique_id", "ds", "y")


def build_long_panel(raw: pd.DataFrame, geometry: GameGeometry) -> pd.DataFrame:
    """Compile immutable wide draw data into StatsForecast long format.

    No sorting, deduplication, gap filling, interpolation, or value repair is performed.
    """

    source = raw.copy(deep=True)
    required = {geometry.time_axis.source_column, *geometry.positions}
    missing = sorted(required.difference(source.columns))
    if missing:
        raise ValueError(f"missing required columns: {missing}")
    if source.empty:
        raise ValueError("raw data must not be empty")

    axis = source[geometry.time_axis.source_column]
    if axis.isna().any() or axis.duplicated().any() or not axis.is_monotonic_increasing:
        raise ValueError("time axis must be complete, unique, and monotonically increasing")
    if geometry.time_axis.mode is TimeAxisMode.DRAW_SEQUENCE:
        numeric = pd.to_numeric(axis, errors="coerce")
        if numeric.isna().any() or not np.equal(numeric, np.floor(numeric)).all():
            raise ValueError("draw_sequence axis must contain integers")
        values = numeric.astype("int64").to_numpy()
        if len(values) > 1 and not np.equal(np.diff(values), 1).all():
            raise ValueError("draw_sequence axis must be gap-free")
        source[geometry.time_axis.source_column] = values
    else:
        parsed = pd.to_datetime(axis, errors="coerce")
        if parsed.isna().any():
            raise ValueError("calendar_time axis must contain valid datetimes")
        source[geometry.time_axis.source_column] = parsed

    frames: list[pd.DataFrame] = []
    for position in geometry.positions:
        y = pd.to_numeric(source[position], errors="coerce")
        if y.isna().any() or not np.isfinite(y.to_numpy(dtype=float)).all():
            raise ValueError(f"position {position} contains missing or non-finite values")
        if ((y < geometry.candidate_min) | (y > geometry.candidate_max)).any():
            raise ValueError(f"position {position} violates candidate range")
        frames.append(
            pd.DataFrame(
                {
                    "unique_id": position,
                    "ds": source[geometry.time_axis.source_column].to_numpy(copy=True),
                    "y": y.to_numpy(dtype=float, copy=True),
                }
            )
        )
    panel = pd.concat(frames, ignore_index=True)
    validate_long_panel(panel, expected_series=len(geometry.positions))
    return panel


def validate_long_panel(panel: pd.DataFrame, *, expected_series: int | None = None) -> None:
    missing = [column for column in _REQUIRED_LONG_COLUMNS if column not in panel]
    if missing:
        raise ValueError(f"long panel is missing columns: {missing}")
    if panel.empty:
        raise ValueError("long panel must not be empty")
    if panel[list(_REQUIRED_LONG_COLUMNS)].isna().any().any():
        raise ValueError("long panel contains missing values")
    if panel.duplicated(["unique_id", "ds"]).any():
        raise ValueError("long panel contains duplicate series/time identities")
    if not np.isfinite(panel["y"].to_numpy(dtype=float)).all():
        raise ValueError("long panel target contains non-finite values")
    for unique_id, group in panel.groupby("unique_id", sort=False):
        if not group["ds"].is_monotonic_increasing:
            raise ValueError(f"series {unique_id} is not chronological")
    if expected_series is not None and panel["unique_id"].nunique() != expected_series:
        raise ValueError("long panel series count does not match game geometry")


def chronological_split(
    panel: pd.DataFrame,
    *,
    validation_size: int,
    holdout_size: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    validate_long_panel(panel)
    if validation_size < 1 or holdout_size < 1:
        raise ValueError("validation_size and holdout_size must be positive")
    train_parts: list[pd.DataFrame] = []
    validation_parts: list[pd.DataFrame] = []
    holdout_parts: list[pd.DataFrame] = []
    for unique_id, group in panel.groupby("unique_id", sort=False):
        minimum = validation_size + holdout_size + 1
        if len(group) < minimum:
            raise ValueError(f"series {unique_id} requires at least {minimum} rows")
        holdout_start = len(group) - holdout_size
        validation_start = holdout_start - validation_size
        train_parts.append(group.iloc[:validation_start])
        validation_parts.append(group.iloc[validation_start:holdout_start])
        holdout_parts.append(group.iloc[holdout_start:])
    return (
        pd.concat(train_parts, ignore_index=True),
        pd.concat(validation_parts, ignore_index=True),
        pd.concat(holdout_parts, ignore_index=True),
    )

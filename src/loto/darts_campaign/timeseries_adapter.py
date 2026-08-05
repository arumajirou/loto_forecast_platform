from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .protocol import GameGeometry


@dataclass(frozen=True)
class PositionLocalPayload:
    series: tuple[pd.Series, ...]
    columns: tuple[str, ...]


@dataclass(frozen=True)
class MultivariatePayload:
    frame: pd.DataFrame
    columns: tuple[str, ...]


def validate_panel(frame: pd.DataFrame, geometry: GameGeometry) -> pd.DataFrame:
    """Validate without sorting, repairing, filling, or mutating the caller's frame."""

    required = [geometry.draw_no_col, *geometry.position_columns]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")
    if frame.empty:
        raise ValueError("panel must not be empty")

    draw_no = pd.to_numeric(frame[geometry.draw_no_col], errors="raise").to_numpy()
    if not np.equal(draw_no, np.floor(draw_no)).all():
        raise ValueError("draw_no must contain integers")
    draw_no = draw_no.astype(np.int64)
    if len(np.unique(draw_no)) != len(draw_no):
        raise ValueError("draw_no must be unique")
    if len(draw_no) > 1 and not np.all(np.diff(draw_no) == 1):
        raise ValueError("draw_no must be strictly increasing and gap-free")

    values = frame[geometry.position_columns].apply(pd.to_numeric, errors="raise").to_numpy(float)
    if not np.isfinite(values).all():
        raise ValueError("position values must be finite")
    if np.any(values < geometry.min_value) or np.any(values > geometry.max_value):
        raise ValueError("position values are outside GameGeometry range")
    return frame.copy(deep=True)


def build_position_local(frame: pd.DataFrame, geometry: GameGeometry) -> PositionLocalPayload:
    validated = validate_panel(frame, geometry)
    index = pd.RangeIndex(
        start=int(validated[geometry.draw_no_col].iloc[0]),
        stop=int(validated[geometry.draw_no_col].iloc[-1]) + 1,
        step=1,
        name=geometry.draw_no_col,
    )
    values = tuple(
        pd.Series(validated[column].to_numpy(float), index=index, name=column)
        for column in geometry.position_columns
    )
    return PositionLocalPayload(values, tuple(geometry.position_columns))


def build_position_multivariate(
    frame: pd.DataFrame, geometry: GameGeometry
) -> MultivariatePayload:
    validated = validate_panel(frame, geometry)
    index = pd.RangeIndex(
        start=int(validated[geometry.draw_no_col].iloc[0]),
        stop=int(validated[geometry.draw_no_col].iloc[-1]) + 1,
        step=1,
        name=geometry.draw_no_col,
    )
    values = validated[geometry.position_columns].copy(deep=True)
    values.index = index
    return MultivariatePayload(values, tuple(geometry.position_columns))


def to_darts_local(payload: PositionLocalPayload, timeseries_cls: Any | None = None) -> list[Any]:
    if timeseries_cls is None:
        from darts import TimeSeries

        timeseries_cls = TimeSeries
    return [timeseries_cls.from_series(series) for series in payload.series]


def to_darts_multivariate(payload: MultivariatePayload, timeseries_cls: Any | None = None) -> Any:
    if timeseries_cls is None:
        from darts import TimeSeries

        timeseries_cls = TimeSeries
    return timeseries_cls.from_dataframe(payload.frame)

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from loto.mlforecast.contracts import MLForecastRunConfig


def validate_panel(frame: pd.DataFrame, config: MLForecastRunConfig) -> pd.DataFrame:
    required = {config.id_col, config.time_col, config.target_col}
    if missing := required - set(frame.columns):
        raise ValueError(f"input data is missing required columns: {sorted(missing)}")
    result = frame.copy()
    if result[list(required)].isna().any().any():
        raise ValueError("id, time and target columns cannot contain missing values")
    if result.duplicated([config.id_col, config.time_col]).any():
        raise ValueError("duplicate id/time rows are not allowed")
    result[config.target_col] = pd.to_numeric(result[config.target_col], errors="raise")
    if not np.isfinite(result[config.target_col].to_numpy(float)).all():
        raise ValueError("target values must be finite")
    result = result.sort_values([config.id_col, config.time_col]).reset_index(drop=True)
    for series_id, group in result.groupby(config.id_col, sort=False):
        if len(group) <= config.holdout_size:
            raise ValueError(f"series {series_id!r} requires more than {config.holdout_size} rows")
        timestamps = group[config.time_col]
        if not timestamps.is_monotonic_increasing or timestamps.duplicated().any():
            raise ValueError(f"series {series_id!r} has invalid time ordering")
    return result


def chronological_split(
    frame: pd.DataFrame,
    config: MLForecastRunConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_parts: list[pd.DataFrame] = []
    holdout_parts: list[pd.DataFrame] = []
    for _, group in frame.groupby(config.id_col, sort=False):
        group = group.sort_values(config.time_col)
        train_parts.append(group.iloc[: -config.holdout_size])
        holdout_parts.append(group.iloc[-config.holdout_size :])
    train = pd.concat(train_parts, ignore_index=True)
    holdout = pd.concat(holdout_parts, ignore_index=True)
    for series_id in train[config.id_col].unique():
        train_max = train.loc[train[config.id_col] == series_id, config.time_col].max()
        holdout_min = holdout.loc[holdout[config.id_col] == series_id, config.time_col].min()
        if train_max >= holdout_min:
            raise ValueError(f"chronological split failed for series {series_id!r}")
    return train, holdout


def load_config(path: Path) -> MLForecastRunConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("configuration root must be a mapping")
    return MLForecastRunConfig.model_validate(payload)


def load_frame(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"unsupported data format: {path.suffix}")

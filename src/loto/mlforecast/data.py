from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from loto.mlforecast.contracts import MLForecastRunConfig, RunMode


def _weight_column(config: MLForecastRunConfig) -> str | None:
    return config.core.weight_col if config.mode is RunMode.CORE else config.auto.weight_col


def _normalize_time(values: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(values) or pd.api.types.is_numeric_dtype(values):
        return values
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().all():
        return numeric
    parsed = pd.to_datetime(values, errors="coerce", utc=False)
    if parsed.notna().all():
        return parsed
    raise ValueError("time column must contain only numeric or timestamp values")


def _validate_declared_features(frame: pd.DataFrame, config: MLForecastRunConfig) -> None:
    weight_col = _weight_column(config)
    declared = set(config.static_features) | set(config.known_future_features)
    if weight_col is not None:
        declared.add(weight_col)
    required = {config.id_col, config.time_col, config.target_col} | declared
    if missing := required - set(frame.columns):
        raise ValueError(f"input data is missing declared columns: {sorted(missing)}")
    extra = set(frame.columns) - required
    if extra:
        raise ValueError(
            "all non-contract columns must be declared as static_features, "
            f"known_future_features, or weight_col; unclassified={sorted(extra)}"
        )
    feature_columns = [*config.static_features, *config.known_future_features]
    if feature_columns and frame[feature_columns].isna().any().any():
        raise ValueError("declared feature columns cannot contain missing values")
    for feature in config.static_features:
        counts = frame.groupby(config.id_col, sort=False)[feature].nunique(dropna=False)
        invalid_ids = counts[counts != 1].index.tolist()
        if invalid_ids:
            raise ValueError(
                f"static feature {feature!r} changes within series: {invalid_ids[:10]}"
            )
    if weight_col is not None:
        weights = pd.to_numeric(frame[weight_col], errors="raise").to_numpy(float)
        if not np.isfinite(weights).all() or np.any(weights < 0):
            raise ValueError("weight values must be finite and non-negative")


def validate_panel(frame: pd.DataFrame, config: MLForecastRunConfig) -> pd.DataFrame:
    required = {config.id_col, config.time_col, config.target_col}
    if missing := required - set(frame.columns):
        raise ValueError(f"input data is missing required columns: {sorted(missing)}")
    result = frame.copy()
    if result[list(required)].isna().any().any():
        raise ValueError("id, time and target columns cannot contain missing values")
    result[config.time_col] = _normalize_time(result[config.time_col])
    if result.duplicated([config.id_col, config.time_col]).any():
        raise ValueError("duplicate id/time rows are not allowed")
    result[config.target_col] = pd.to_numeric(result[config.target_col], errors="raise")
    if not np.isfinite(result[config.target_col].to_numpy(float)).all():
        raise ValueError("target values must be finite")
    _validate_declared_features(result, config)

    for series_id, group in result.groupby(config.id_col, sort=False):
        if len(group) <= config.holdout_size:
            raise ValueError(f"series {series_id!r} requires more than {config.holdout_size} rows")
        timestamps = group[config.time_col]
        if not timestamps.is_monotonic_increasing:
            raise ValueError(f"series {series_id!r} is not chronologically ordered in input")

    return result.sort_values([config.id_col, config.time_col]).reset_index(drop=True)


def chronological_split(
    frame: pd.DataFrame,
    config: MLForecastRunConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_parts: list[pd.DataFrame] = []
    holdout_parts: list[pd.DataFrame] = []
    for _, group in frame.groupby(config.id_col, sort=False):
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


def validate_future_features(
    frame: pd.DataFrame | None,
    *,
    expected_keys: pd.DataFrame,
    config: MLForecastRunConfig,
) -> pd.DataFrame | None:
    features = config.known_future_features
    if not features:
        if frame is not None and not frame.empty:
            raise ValueError("future feature data was supplied but known_future_features is empty")
        return None
    if frame is None:
        raise ValueError("future feature data is required for declared known_future_features")
    required = [config.id_col, config.time_col, *features]
    if missing := set(required) - set(frame.columns):
        raise ValueError(f"future feature data is missing columns: {sorted(missing)}")
    if extra := set(frame.columns) - set(required):
        raise ValueError(f"future feature data contains unclassified columns: {sorted(extra)}")
    result = frame[required].copy()
    result[config.time_col] = _normalize_time(result[config.time_col])
    if result[required].isna().any().any():
        raise ValueError("future feature data cannot contain missing values")
    if result.duplicated([config.id_col, config.time_col]).any():
        raise ValueError("future feature data contains duplicate id/time rows")

    keys = [config.id_col, config.time_col]
    expected = expected_keys[keys].sort_values(keys).reset_index(drop=True)
    actual = result[keys].sort_values(keys).reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(expected, actual, check_dtype=False)
    except AssertionError as exc:
        raise ValueError("future feature id/time rows do not match the forecast horizon") from exc
    return result.sort_values(keys).reset_index(drop=True)


def load_config(path: Path) -> MLForecastRunConfig:
    payload: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
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

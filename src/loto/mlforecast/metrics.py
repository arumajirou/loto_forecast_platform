from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


METRIC_NAMES = ("hit_at_1", "all_position_hit_at_1", "mae", "mse", "rmse")


def _aligned_values(
    actual: pd.DataFrame,
    predicted: pd.DataFrame,
    *,
    prediction_col: str,
    id_col: str,
    time_col: str,
    target_col: str,
) -> pd.DataFrame:
    required_actual = {id_col, time_col, target_col}
    required_predicted = {id_col, time_col, prediction_col}
    if missing := required_actual - set(actual.columns):
        raise ValueError(f"actual dataframe is missing columns: {sorted(missing)}")
    if missing := required_predicted - set(predicted.columns):
        raise ValueError(f"prediction dataframe is missing columns: {sorted(missing)}")
    merged = actual[[id_col, time_col, target_col]].merge(
        predicted[[id_col, time_col, prediction_col]],
        on=[id_col, time_col],
        how="inner",
        validate="one_to_one",
    )
    if len(merged) != len(actual) or len(merged) != len(predicted):
        raise ValueError("actual and prediction keys do not align exactly")
    values = merged[[target_col, prediction_col]].to_numpy(float)
    if not np.isfinite(values).all():
        raise ValueError("actual or prediction values contain NaN or Inf")
    return merged


def evaluate_prediction(
    actual: pd.DataFrame,
    predicted: pd.DataFrame,
    *,
    prediction_col: str,
    id_col: str,
    time_col: str,
    target_col: str,
) -> tuple[dict[str, float], pd.DataFrame]:
    merged = _aligned_values(
        actual,
        predicted,
        prediction_col=prediction_col,
        id_col=id_col,
        time_col=time_col,
        target_col=target_col,
    )
    merged["absolute_error"] = np.abs(merged[prediction_col] - merged[target_col])
    merged["squared_error"] = np.square(merged[prediction_col] - merged[target_col])
    merged["hit_at_1"] = merged["absolute_error"] <= 1.0

    overall: dict[str, float] = {
        "hit_at_1": float(merged["hit_at_1"].mean()),
        "all_position_hit_at_1": float(merged.groupby(time_col)["hit_at_1"].all().mean()),
        "mae": float(merged["absolute_error"].mean()),
        "mse": float(merged["squared_error"].mean()),
        "rmse": float(np.sqrt(merged["squared_error"].mean())),
    }
    by_position = (
        merged.groupby(id_col, sort=True)
        .agg(
            hit_at_1=("hit_at_1", "mean"),
            mae=("absolute_error", "mean"),
            mse=("squared_error", "mean"),
        )
        .reset_index()
    )
    by_position["rmse"] = np.sqrt(by_position["mse"])
    return overall, by_position


def make_baseline_predictions(
    train: pd.DataFrame,
    future: pd.DataFrame,
    *,
    id_col: str,
    time_col: str,
    target_col: str,
    seed: int,
    fixed_value: float | None,
    season_length: int,
) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    outputs: dict[str, list[dict[str, Any]]] = {
        "baseline_random": [],
        "baseline_fixed": [],
        "baseline_mean": [],
        "baseline_median": [],
        "baseline_last": [],
        "baseline_frequency": [],
        "baseline_seasonal_naive": [],
    }
    for series_id, future_group in future.groupby(id_col, sort=True):
        history = train.loc[train[id_col] == series_id].sort_values(time_col)
        values = history[target_col].to_numpy(float)
        if values.size == 0:
            raise ValueError(f"no training rows for series {series_id!r}")
        mode = pd.Series(values).mode().iloc[0]
        fixed = float(np.median(values) if fixed_value is None else fixed_value)
        for step, row in enumerate(future_group.sort_values(time_col).itertuples(index=False)):
            key = {id_col: series_id, time_col: getattr(row, time_col)}
            seasonal_index = max(0, values.size - season_length + (step % season_length))
            forecasts = {
                "baseline_random": float(rng.choice(values)),
                "baseline_fixed": fixed,
                "baseline_mean": float(np.mean(values)),
                "baseline_median": float(np.median(values)),
                "baseline_last": float(values[-1]),
                "baseline_frequency": float(mode),
                "baseline_seasonal_naive": float(values[seasonal_index]),
            }
            for name, value in forecasts.items():
                outputs[name].append(key | {name: value})
    return {name: pd.DataFrame(rows) for name, rows in outputs.items()}

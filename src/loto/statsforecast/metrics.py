from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd


def regression_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    y = np.asarray(actual, dtype=float)
    y_hat = np.asarray(predicted, dtype=float)
    if y.shape != y_hat.shape or y.size == 0:
        raise ValueError("actual and predicted must have the same non-empty shape")
    if not np.isfinite(y).all() or not np.isfinite(y_hat).all():
        raise ValueError("metrics require finite values")
    error = y_hat - y
    return {
        "hit_at_pm1": float(np.mean(np.abs(error) <= 1.0)),
        "mae": float(np.mean(np.abs(error))),
        "mse": float(np.mean(np.square(error))),
        "rmse": float(np.sqrt(np.mean(np.square(error)))),
    }


def evaluate_prediction_frame(frame: pd.DataFrame) -> dict[str, object]:
    required = {"unique_id", "ds", "actual", "prediction"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"prediction frame is missing columns: {missing}")
    if frame.duplicated(["unique_id", "ds"]).any():
        raise ValueError("prediction frame contains duplicate identities")
    overall = regression_metrics(frame["actual"].to_numpy(), frame["prediction"].to_numpy())
    position_metrics = {
        str(unique_id): regression_metrics(
            group["actual"].to_numpy(),
            group["prediction"].to_numpy(),
        )
        for unique_id, group in frame.groupby("unique_id", sort=False)
    }
    per_draw = frame.assign(
        hit=(frame["prediction"].sub(frame["actual"]).abs() <= 1.0)
    ).groupby("ds", sort=False)["hit"].all()
    return {
        **overall,
        "all_position_hit_at_pm1": float(per_draw.mean()),
        "position_metrics": position_metrics,
    }


def baseline_prediction(
    train: np.ndarray,
    *,
    horizon: int,
    strategy: str,
    seed: int = 1,
    fixed_value: float | None = None,
    season_length: int = 1,
) -> np.ndarray:
    values = np.asarray(train, dtype=float)
    if values.ndim != 1 or values.size == 0 or not np.isfinite(values).all():
        raise ValueError("train must be a finite one-dimensional array")
    if horizon < 1:
        raise ValueError("horizon must be positive")
    if strategy == "random":
        rng = np.random.default_rng(seed)
        return rng.choice(values, size=horizon, replace=True).astype(float)
    if strategy == "fixed":
        if fixed_value is None:
            raise ValueError("fixed baseline requires fixed_value")
        return np.full(horizon, fixed_value, dtype=float)
    if strategy == "mean":
        return np.full(horizon, np.mean(values), dtype=float)
    if strategy == "median":
        return np.full(horizon, np.median(values), dtype=float)
    if strategy == "last":
        return np.full(horizon, values[-1], dtype=float)
    if strategy == "frequency":
        counts = Counter(values.tolist())
        most_common = min(value for value, count in counts.items() if count == max(counts.values()))
        return np.full(horizon, most_common, dtype=float)
    if strategy == "seasonal_naive":
        if season_length < 1 or values.size < season_length:
            raise ValueError("seasonal_naive requires enough history")
        season = values[-season_length:]
        return np.resize(season, horizon).astype(float)
    raise ValueError(f"unsupported baseline strategy: {strategy}")

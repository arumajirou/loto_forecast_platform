from __future__ import annotations

import numpy as np
import pandas as pd


def select_point_column(predictions: pd.DataFrame, alias: str) -> str:
    candidates = [
        alias,
        f"{alias}-median",
        f"{alias}-mean",
    ]
    for candidate in candidates:
        if candidate in predictions.columns:
            return candidate
    numeric = [
        column
        for column in predictions.columns
        if column not in {"unique_id", "ds", "cutoff"}
        and pd.api.types.is_numeric_dtype(predictions[column])
        and "-lo-" not in column
        and "-hi-" not in column
        and not column.endswith(("-loc", "-scale", "-df"))
    ]
    if not numeric:
        raise ValueError(f"no point prediction column found; columns={list(predictions.columns)}")
    return numeric[0]


def score_vector(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    if actual.shape != predicted.shape:
        raise ValueError(f"shape mismatch: actual={actual.shape}, predicted={predicted.shape}")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("non-finite metric input")
    error = predicted - actual
    absolute = np.abs(error)
    return {
        "hit_pm1": float(np.mean(absolute <= 1.0)),
        "exact_hit": float(np.mean(absolute == 0.0)),
        "mae": float(np.mean(absolute)),
        "mse": float(np.mean(error**2)),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "count": float(actual.size),
    }


def score_draw_matrix(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    metrics = score_vector(actual, predicted)
    absolute = np.abs(np.asarray(predicted, dtype=float) - np.asarray(actual, dtype=float))
    if absolute.ndim == 1:
        absolute = absolute.reshape(1, -1)
    metrics["all_positions_hit_pm1"] = float(np.mean(np.all(absolute <= 1.0, axis=1)))
    return metrics


def aggregate_seed_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"model", "track", "seed", "hit_pm1", "mae", "mse", "rmse"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing metric columns: {sorted(missing)}")
    aggregations: dict[str, list[str]] = {
        "hit_pm1": ["mean", "std", "min", "max"],
        "mae": ["mean", "std", "min", "max"],
        "mse": ["mean", "std", "min", "max"],
        "rmse": ["mean", "std", "min", "max"],
    }
    grouped = frame.groupby(["model", "track"], dropna=False).agg(aggregations)
    grouped.columns = [f"{metric}_{stat}" for metric, stat in grouped.columns]
    return grouped.reset_index()


def rank_validation_trials(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "hit_pm1",
        "all_positions_hit_pm1",
        "mae",
        "rmse",
        "worst_seed_hit_pm1",
        "failure_rate",
    ]  # noqa: E501
    for column in columns:
        if column not in frame.columns:
            frame[column] = (
                0.0
                if column in {"hit_pm1", "all_positions_hit_pm1", "worst_seed_hit_pm1"}
                else np.inf
            )  # noqa: E501
    return frame.sort_values(
        columns,
        ascending=[False, False, True, True, False, True],
        kind="stable",
    ).reset_index(drop=True)


def nearest_unique_sorted(
    values: np.ndarray,
    *,
    lower: int = 1,
    upper: int = 31,
) -> np.ndarray:
    """Project one draw to the nearest strictly increasing integer sequence."""

    raw = np.asarray(values, dtype=float).reshape(-1)
    count = raw.size
    if count < 1 or upper - lower + 1 < count:
        raise ValueError("invalid reconciliation bounds")
    numbers = np.arange(lower, upper + 1, dtype=int)
    costs = (numbers[None, :] - raw[:, None]) ** 2
    infinity = float("inf")
    dp = np.full((count, len(numbers)), infinity, dtype=float)
    previous = np.full((count, len(numbers)), -1, dtype=int)
    dp[0] = costs[0]
    for position in range(1, count):
        best_cost = infinity
        best_index = -1
        for index in range(len(numbers)):
            candidate = index - 1
            if candidate >= 0 and dp[position - 1, candidate] < best_cost:
                best_cost = dp[position - 1, candidate]
                best_index = candidate
            if best_index >= 0:
                dp[position, index] = best_cost + costs[position, index]
                previous[position, index] = best_index
    last = int(np.argmin(dp[-1]))
    if not np.isfinite(dp[-1, last]):
        raise RuntimeError("failed to reconcile prediction")
    chosen = [last]
    for position in range(count - 1, 0, -1):
        last = int(previous[position, last])
        chosen.append(last)
    chosen.reverse()
    return numbers[np.asarray(chosen, dtype=int)].astype(float)


def prediction_variants(values: np.ndarray) -> dict[str, np.ndarray]:
    raw = np.asarray(values, dtype=float).reshape(-1)
    rounded = np.clip(np.rint(raw), 1, 31)
    variants = {"raw": raw, "rounded": rounded}
    if raw.size > 1:
        variants["reconciled"] = nearest_unique_sorted(raw)
    return variants

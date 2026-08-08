from __future__ import annotations

from typing import Any

import numpy as np


def evaluate_predictions(actual: np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    actual_values = np.asarray(actual, dtype=float)
    predicted_values = np.asarray(predicted, dtype=float)
    if actual_values.shape != predicted_values.shape or actual_values.ndim != 2:
        raise ValueError("actual and predicted must be same-shape [draw, position] arrays")
    if not np.isfinite(actual_values).all() or not np.isfinite(predicted_values).all():
        raise ValueError("metrics require finite arrays")

    error = predicted_values - actual_values
    absolute_error = np.abs(error)
    hit_matrix = absolute_error <= 1.0
    hit_at_plus_minus_1 = float(hit_matrix.mean())
    all_position_hit_at_plus_minus_1 = float(hit_matrix.all(axis=1).mean())
    position_hit_at_plus_minus_1 = hit_matrix.mean(axis=0).astype(float).tolist()
    return {
        "hit_at_plus_minus_1": hit_at_plus_minus_1,
        "all_position_hit_at_plus_minus_1": all_position_hit_at_plus_minus_1,
        "position_hit_at_plus_minus_1": position_hit_at_plus_minus_1,
        # Compatibility aliases for the pre-conflict PR #56 naming contract.
        "hit_at_1": hit_at_plus_minus_1,
        "all_position_hit_at_1": all_position_hit_at_plus_minus_1,
        "position_hit_at_1": position_hit_at_plus_minus_1,
        "mae": float(absolute_error.mean()),
        "mse": float(np.square(error).mean()),
        "rmse": float(np.sqrt(np.square(error).mean())),
    }


def build_baselines(
    train: np.ndarray,
    horizon: int,
    *,
    seed: int,
    fixed_value: float | None = None,
    season_length: int = 1,
) -> dict[str, np.ndarray]:
    values = np.asarray(train, dtype=float)
    if values.ndim != 2 or len(values) < 2 or horizon < 1:
        raise ValueError("train must be [time, position] with at least two rows")
    if not np.isfinite(values).all():
        raise ValueError("baseline training data must be finite")

    positions = values.shape[1]
    rng = np.random.default_rng(seed)
    low = np.floor(values.min(axis=0)).astype(int)
    high = np.ceil(values.max(axis=0)).astype(int) + 1
    random = np.column_stack(
        [rng.integers(low[index], high[index], size=horizon) for index in range(positions)]
    ).astype(float)

    modes: list[float] = []
    for index in range(positions):
        unique, counts = np.unique(values[:, index], return_counts=True)
        modes.append(float(unique[np.argmax(counts)]))

    seasonal_source = values[-season_length:] if season_length <= len(values) else values[-1:]
    seasonal = np.vstack(
        [seasonal_source[index % len(seasonal_source)] for index in range(horizon)]
    )
    fixed = float(np.median(values)) if fixed_value is None else float(fixed_value)
    return {
        "random": random,
        "fixed": np.full((horizon, positions), fixed, dtype=float),
        "mean": np.tile(values.mean(axis=0), (horizon, 1)),
        "median": np.tile(np.median(values, axis=0), (horizon, 1)),
        "last": np.tile(values[-1], (horizon, 1)),
        "frequency": np.tile(np.asarray(modes), (horizon, 1)),
        "seasonal_naive": seasonal,
    }

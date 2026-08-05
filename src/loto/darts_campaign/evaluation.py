from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from .protocol import EvaluationPolicy, GameGeometry


def _matrix(values: list[list[float]] | np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 2:
        raise ValueError(f"expected position x horizon matrix, got shape={array.shape}")
    if not np.isfinite(array).all():
        raise ValueError("values contain NaN or Inf")
    return array


def evaluate_predictions(
    actual: list[list[float]] | np.ndarray,
    predicted: list[list[float]] | np.ndarray,
    *,
    tolerance: float = 1.0,
) -> dict[str, Any]:
    y_true = _matrix(actual)
    y_pred = _matrix(predicted)
    if y_true.shape != y_pred.shape:
        raise ValueError(f"shape mismatch: actual={y_true.shape}, predicted={y_pred.shape}")
    errors = y_pred - y_true
    absolute = np.abs(errors)
    squared = np.square(errors)
    hits = absolute <= tolerance
    return {
        "hit_at_plus_minus_1": float(hits.mean()),
        "position_hit_at_plus_minus_1": [float(value) for value in hits.mean(axis=1)],
        "all_position_hit_at_plus_minus_1": float(hits.all(axis=0).mean()),
        "mae": float(absolute.mean()),
        "mse": float(squared.mean()),
        "rmse": float(np.sqrt(squared.mean())),
        "positions": int(y_true.shape[0]),
        "horizon": int(y_true.shape[1]),
        "tolerance": float(tolerance),
    }


def _frequency_value(values: np.ndarray) -> float:
    counts = Counter(float(value) for value in values)
    highest = max(counts.values())
    return min(value for value, count in counts.items() if count == highest)


def generate_baselines(
    train: pd.DataFrame,
    geometry: GameGeometry,
    policy: EvaluationPolicy,
    *,
    seed: int,
) -> dict[str, np.ndarray]:
    horizon = policy.holdout_size
    matrix = train[geometry.position_columns].to_numpy(dtype=float).T
    if matrix.shape[1] < 1:
        raise ValueError("baseline generation requires non-empty training data")
    fixed = (
        float(policy.fixed_value)
        if policy.fixed_value is not None
        else float((geometry.min_value + geometry.max_value) / 2.0)
    )
    rng = np.random.default_rng(seed)
    results: dict[str, np.ndarray] = {}
    for name in policy.baselines:
        if name == "random":
            values = rng.integers(
                geometry.min_value,
                geometry.max_value + 1,
                size=(geometry.positions, horizon),
            ).astype(float)
        elif name == "fixed":
            values = np.full((geometry.positions, horizon), fixed, dtype=float)
        elif name == "mean":
            values = np.repeat(matrix.mean(axis=1, keepdims=True), horizon, axis=1)
        elif name == "median":
            values = np.repeat(np.median(matrix, axis=1, keepdims=True), horizon, axis=1)
        elif name == "last":
            values = np.repeat(matrix[:, -1:], horizon, axis=1)
        elif name == "frequency":
            modes = np.asarray([_frequency_value(row) for row in matrix], dtype=float)
            values = np.repeat(modes[:, None], horizon, axis=1)
        elif name == "seasonal_naive":
            season = min(policy.season_length, matrix.shape[1])
            source = matrix[:, -season:]
            values = np.column_stack([source[:, index % season] for index in range(horizon)])
        else:
            raise ValueError(f"unsupported baseline: {name}")
        results[name] = values
    return results

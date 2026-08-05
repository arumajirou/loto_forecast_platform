from __future__ import annotations

import math
from typing import Any

import numpy as np


def evaluate_predictions(actual: np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    """Evaluate predictions with Hit@±1 as the primary metric."""

    truth = np.asarray(actual, dtype=float)
    forecast = np.asarray(predicted, dtype=float)
    if truth.shape != forecast.shape:
        raise ValueError(f"shape mismatch: actual={truth.shape}, predicted={forecast.shape}")
    if truth.ndim < 2:
        raise ValueError("predictions must include a position dimension")
    if not np.isfinite(truth).all() or not np.isfinite(forecast).all():
        raise ValueError("metrics require finite actual and predicted values")

    error = forecast - truth
    absolute = np.abs(error)
    hit = absolute <= 1.0
    reduce_axes = tuple(range(truth.ndim - 1))
    position_hit = np.mean(hit, axis=reduce_axes)
    per_draw_hit = np.all(hit, axis=-1)
    return {
        "hit_at_1": float(np.mean(hit)),
        "position_hit_at_1": [float(value) for value in np.ravel(position_hit)],
        "all_position_hit_at_1": float(np.mean(per_draw_hit)),
        "mae": float(np.mean(absolute)),
        "mse": float(np.mean(np.square(error))),
        "rmse": float(math.sqrt(np.mean(np.square(error)))),
        "shape": list(truth.shape),
    }

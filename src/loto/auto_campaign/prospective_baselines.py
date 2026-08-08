"""Leakage-safe deterministic baselines for Prospective scoring."""

from __future__ import annotations

from typing import Any

import numpy as np

from .metrics import nearest_unique_sorted

BASELINE_NAMES = (
    "random_uniform",
    "fixed_center",
    "mean",
    "median",
    "last",
    "frequency",
    "statistical_ar1",
)


def _repeat(vector: np.ndarray, horizon: int) -> np.ndarray:
    return np.repeat(np.asarray(vector, dtype=float).reshape(1, -1), horizon, axis=0)


def _reconcile_rows(values: np.ndarray, *, lower: int, upper: int) -> np.ndarray:
    matrix = np.asarray(values, dtype=float)
    return np.vstack([nearest_unique_sorted(row, lower=lower, upper=upper) for row in matrix])


def _fixed_center_vector(
    position_count: int,
    *,
    lower: int,
    upper: int,
) -> np.ndarray:
    """Return a history-independent fixed sequence across the allowed domain."""

    anchors = np.linspace(lower, upper, position_count + 2, dtype=float)[1:-1]
    return nearest_unique_sorted(anchors, lower=lower, upper=upper)


def _frequency_vector(history: np.ndarray, *, lower: int, upper: int) -> np.ndarray:
    flattened = np.asarray(history, dtype=int).reshape(-1)
    counts = {value: 0 for value in range(lower, upper + 1)}
    for value in flattened:
        if lower <= int(value) <= upper:
            counts[int(value)] += 1
    count = history.shape[1]
    selected = sorted(counts, key=lambda value: (-counts[value], value))[:count]
    return np.asarray(sorted(selected), dtype=float)


def _ar1_forecast(series: np.ndarray, horizon: int) -> tuple[np.ndarray, bool]:
    values = np.asarray(series, dtype=float).reshape(-1)
    if values.size < 3 or np.allclose(values[:-1], values[:-1].mean()):
        return np.repeat(values[-1], horizon), True
    design = np.column_stack([np.ones(values.size - 1), values[:-1]])
    target = values[1:]
    coefficients, *_ = np.linalg.lstsq(design, target, rcond=None)
    intercept, phi = (float(coefficients[0]), float(coefficients[1]))
    predictions: list[float] = []
    current = float(values[-1])
    for _ in range(horizon):
        current = intercept + phi * current
        predictions.append(current)
    result = np.asarray(predictions, dtype=float)
    if not np.isfinite(result).all():
        return np.repeat(values[-1], horizon), True
    return result, False


def generate_prospective_baselines(
    history: np.ndarray,
    *,
    horizon: int,
    lower: int = 1,
    upper: int = 31,
    random_seed: int = 1,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Generate baselines using prediction-time history only.

    Every returned matrix has shape ``(horizon, n_positions)``. Actual values are
    intentionally absent from the API so baseline fitting cannot consume them.
    The ``fixed_center`` baseline is independent of both history and actuals.
    """

    matrix = np.asarray(history, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 3 or matrix.shape[1] < 1:
        raise ValueError("history must be a finite two-dimensional matrix")
    if horizon < 1:
        raise ValueError("horizon must be positive")
    if not np.isfinite(matrix).all():
        raise ValueError("history contains non-finite values")
    if upper - lower + 1 < matrix.shape[1]:
        raise ValueError("number range is too small for unique positions")

    rng = np.random.default_rng(random_seed)
    random_rows = np.vstack(
        [
            np.sort(
                rng.choice(
                    np.arange(lower, upper + 1, dtype=int),
                    size=matrix.shape[1],
                    replace=False,
                )
            ).astype(float)
            for _ in range(horizon)
        ]
    )

    fixed_center = _fixed_center_vector(
        matrix.shape[1],
        lower=lower,
        upper=upper,
    )
    mean = matrix.mean(axis=0)
    median = np.median(matrix, axis=0)
    last = matrix[-1]
    frequency = _frequency_vector(matrix, lower=lower, upper=upper)

    statistical_columns: list[np.ndarray] = []
    fallback_positions: list[int] = []
    for position in range(matrix.shape[1]):
        forecast, fallback = _ar1_forecast(matrix[:, position], horizon)
        statistical_columns.append(forecast)
        if fallback:
            fallback_positions.append(position + 1)
    statistical = np.column_stack(statistical_columns)

    baselines = {
        "random_uniform": random_rows,
        "fixed_center": _repeat(fixed_center, horizon),
        "mean": _repeat(mean, horizon),
        "median": _repeat(median, horizon),
        "last": _repeat(last, horizon),
        "frequency": _repeat(frequency, horizon),
        "statistical_ar1": statistical,
    }
    if tuple(baselines) != BASELINE_NAMES:
        raise AssertionError("baseline registry order changed")
    for name, values in baselines.items():
        if values.shape != (horizon, matrix.shape[1]):
            raise AssertionError(f"baseline shape mismatch: {name}={values.shape}")
        if not np.isfinite(values).all():
            raise ValueError(f"baseline contains non-finite values: {name}")

    metadata = {
        "history_rows": int(matrix.shape[0]),
        "position_count": int(matrix.shape[1]),
        "horizon": horizon,
        "lower": lower,
        "upper": upper,
        "random_seed": random_seed,
        "fixed_value_definition": (
            "history-independent evenly spaced domain centers reconciled to "
            "strictly increasing integers"
        ),
        "fixed_value_vector": fixed_center.tolist(),
        "statistical_model": "per-position AR(1) with intercept fitted by least squares",
        "statistical_fallback": "last value when AR(1) is underidentified or non-finite",
        "statistical_fallback_positions": fallback_positions,
        "reconciled_examples": {
            name: _reconcile_rows(values, lower=lower, upper=upper).tolist()
            for name, values in baselines.items()
        },
    }
    return baselines, metadata

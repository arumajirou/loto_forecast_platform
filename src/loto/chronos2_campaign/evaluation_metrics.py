from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from .evaluation_contracts import OOFConfig, PredictionBundle


def _validate_prediction(
    bundle: PredictionBundle,
    config: OOFConfig,
) -> tuple[np.ndarray, dict[float, np.ndarray]]:
    point = np.asarray(bundle.point, dtype=float)
    expected = (len(config.position_columns), config.horizon)
    if point.shape != expected:
        raise ValueError(f"prediction shape {point.shape} does not match {expected}")
    if not np.isfinite(point).all():
        raise ValueError("prediction contains non-finite values")

    quantiles: dict[float, np.ndarray] = {}
    for key, values in bundle.quantiles.items():
        try:
            level = float(key)
        except ValueError as exc:
            raise ValueError(f"invalid quantile key: {key}") from exc
        matrix = np.asarray(values, dtype=float)
        if matrix.shape != expected:
            raise ValueError(f"quantile {key} shape {matrix.shape} does not match {expected}")
        if not np.isfinite(matrix).all():
            raise ValueError(f"quantile {key} contains non-finite values")
        quantiles[level] = matrix

    ordered_levels = sorted(quantiles)
    for position_index in range(expected[0]):
        for horizon_index in range(expected[1]):
            values = [quantiles[level][position_index, horizon_index] for level in ordered_levels]
            if values != sorted(values):
                raise ValueError(
                    "quantile crossing detected at "
                    f"position={position_index}, horizon={horizon_index}"
                )
    return point, quantiles


def _point_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = predicted - actual
    absolute = np.abs(error)
    hit = absolute <= 1.0
    return {
        "hit_at_1": float(hit.mean()),
        "all_position_hit_at_1": float(hit.all(axis=0).mean()),
        "mae": float(absolute.mean()),
        "mse": float(np.square(error).mean()),
        "rmse": float(np.sqrt(np.square(error).mean())),
    }


def _position_metrics(actual: np.ndarray, predicted: np.ndarray) -> list[dict[str, float]]:
    absolute = np.abs(predicted - actual)
    squared = np.square(predicted - actual)
    rows: list[dict[str, float]] = []
    for position_index in range(actual.shape[0]):
        rows.append(
            {
                "position_index": float(position_index),
                "hit_at_1": float((absolute[position_index] <= 1.0).mean()),
                "mae": float(absolute[position_index].mean()),
                "mse": float(squared[position_index].mean()),
                "rmse": float(np.sqrt(squared[position_index].mean())),
            }
        )
    return rows


def _probabilistic_metrics(
    actual: np.ndarray,
    quantiles: Mapping[float, np.ndarray],
) -> dict[str, float | None]:
    if not quantiles:
        return {
            "pinball_loss": None,
            "crps_approx": None,
            "coverage_80": None,
            "coverage_90": None,
            "interval_width_80": None,
            "interval_width_90": None,
            "calibration_error": None,
            "quantile_crossing_count": 0.0,
        }

    losses: list[float] = []
    calibration: list[float] = []
    levels = sorted(quantiles)
    for level in levels:
        prediction = quantiles[level]
        residual = actual - prediction
        loss = np.maximum(level * residual, (level - 1.0) * residual)
        losses.append(float(loss.mean()))
        calibration.append(abs(float((actual <= prediction).mean()) - level))

    mean_pinball = float(np.mean(losses))
    result: dict[str, float | None] = {
        "pinball_loss": mean_pinball,
        "crps_approx": 2.0 * mean_pinball,
        "calibration_error": float(np.mean(calibration)),
        "quantile_crossing_count": 0.0,
    }
    for label, lower, upper in (("80", 0.1, 0.9), ("90", 0.05, 0.95)):
        if lower in quantiles and upper in quantiles:
            lower_values = quantiles[lower]
            upper_values = quantiles[upper]
            inside = (actual >= lower_values) & (actual <= upper_values)
            result[f"coverage_{label}"] = float(inside.mean())
            result[f"interval_width_{label}"] = float(
                (upper_values - lower_values).mean()
            )
        else:
            result[f"coverage_{label}"] = None
            result[f"interval_width_{label}"] = None
    return result

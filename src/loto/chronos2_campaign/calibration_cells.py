from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from .calibration_contracts import CalibrationConfig
from .calibration_input import _quantile_column
from .calibration_methods import (
    bias_offset,
    finite_sample_conformal_quantile,
    quantile_residual_correction,
    rearrange_quantiles,
)
from .evaluation_metrics import _point_metrics, _probabilistic_metrics

def _cell_rows(
    selected: pd.DataFrame,
    *,
    fold_ids: Sequence[str],
    seed: int,
    position: str,
    horizon_step: int,
) -> pd.DataFrame:
    rows = selected.loc[
        selected["fold_id"].isin(fold_ids)
        & (selected["seed"] == seed)
        & (selected["position"] == position)
        & (selected["horizon_step"] == horizon_step)
    ].copy()
    order = {fold_id: index for index, fold_id in enumerate(fold_ids)}
    rows["_order"] = rows["fold_id"].map(order)
    return rows.sort_values("_order", kind="stable").drop(columns=["_order"])


def _fit_cell_parameters(
    fit_rows: pd.DataFrame,
    conformal_rows: pd.DataFrame,
    config: CalibrationConfig,
) -> tuple[float, dict[float, float], dict[float, float], int]:
    bias = bias_offset(
        (fit_rows["actual"] - fit_rows["raw_point"]).tolist(),
        config.bias_statistic,
    )
    corrections: dict[float, float] = {}
    for level in config.quantile_levels:
        column = _quantile_column(level)
        corrections[level] = quantile_residual_correction(
            (fit_rows["actual"] - fit_rows[column]).tolist(),
            level,
            config.quantile_correction_method,
        )

    qhats: dict[float, float] = {}
    crossing_rearrangements = 0
    for coverage in config.interval_coverages:
        alpha = 1.0 - coverage
        lower_level = round(alpha / 2.0, 10)
        upper_level = round(1.0 - alpha / 2.0, 10)
        scores: list[float] = []
        for _, row in conformal_rows.iterrows():
            calibrated = {
                level: float(row[_quantile_column(level)]) + corrections[level]
                for level in config.quantile_levels
            }
            calibrated, changed = rearrange_quantiles(calibrated)
            crossing_rearrangements += changed
            lower = calibrated[lower_level]
            upper = calibrated[upper_level]
            actual = float(row["actual"])
            scores.append(max(lower - actual, actual - upper, 0.0))
        qhats[coverage] = finite_sample_conformal_quantile(scores, coverage=coverage)
    return bias, corrections, qhats, crossing_rearrangements


def _target_matrices(
    selected: pd.DataFrame,
    *,
    fold_id: str,
    seed: int,
    config: CalibrationConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[float, np.ndarray]]:
    rows = selected.loc[
        (selected["fold_id"] == fold_id) & (selected["seed"] == seed)
    ].copy()
    position_order = {name: index for index, name in enumerate(config.position_columns)}
    rows["_position_order"] = rows["position"].map(position_order)
    rows = rows.sort_values(["_position_order", "horizon_step"], kind="stable")
    expected = len(config.position_columns) * config.horizon
    if len(rows) != expected:
        raise RuntimeError("target fold grid is incomplete")
    shape = (len(config.position_columns), config.horizon)
    actual = rows["actual"].to_numpy(dtype=float).reshape(shape)
    raw_point = rows["raw_point"].to_numpy(dtype=float).reshape(shape)
    point = rows["point"].to_numpy(dtype=float).reshape(shape)
    quantiles = {
        level: rows[_quantile_column(level)].to_numpy(dtype=float).reshape(shape)
        for level in config.quantile_levels
    }
    return actual, raw_point, point, quantiles


def _prediction_rows(
    *,
    fold_id: str,
    variant: str,
    seed: int,
    config: CalibrationConfig,
    actual: np.ndarray,
    source_raw_point: np.ndarray,
    point: np.ndarray,
    quantiles: Mapping[float, np.ndarray],
    fit_fold_count: int,
    conformal_fold_count: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for position_index, position in enumerate(config.position_columns):
        for horizon_index in range(config.horizon):
            row: dict[str, Any] = {
                "fold_id": fold_id,
                "candidate": variant,
                "seed": seed,
                "position": position,
                "horizon_step": horizon_index + 1,
                "actual": float(actual[position_index, horizon_index]),
                "source_raw_point": float(source_raw_point[position_index, horizon_index]),
                "point": float(point[position_index, horizon_index]),
                "fit_fold_count": fit_fold_count,
                "conformal_fold_count": conformal_fold_count,
            }
            for level, matrix in quantiles.items():
                row[_quantile_column(level)] = float(
                    matrix[position_index, horizon_index]
                )
            rows.append(row)
    return rows


def _metric_row(
    *,
    fold_id: str,
    variant: str,
    seed: int,
    actual: np.ndarray,
    point: np.ndarray,
    quantiles: Mapping[float, np.ndarray],
) -> dict[str, Any]:
    return {
        "fold_id": fold_id,
        "candidate": variant,
        "seed": seed,
        **_point_metrics(actual, point),
        **_probabilistic_metrics(actual, quantiles),
    }


def _comparison(seed_summary: pd.DataFrame) -> pd.DataFrame:
    baseline_rows = seed_summary.loc[
        seed_summary["candidate"] == "chronos2_uncalibrated"
    ]
    if len(baseline_rows) != 1:
        raise RuntimeError("uncalibrated summary row is missing")
    baseline = baseline_rows.iloc[0]
    rows: list[dict[str, Any]] = []
    for _, row in seed_summary.iterrows():
        rows.append(
            {
                "candidate": row["candidate"],
                "hit_at_1_mean": row["hit_at_1_mean"],
                "delta_hit_at_1": row["hit_at_1_mean"] - baseline["hit_at_1_mean"],
                "mae_mean": row["mae_mean"],
                "delta_mae": baseline["mae_mean"] - row["mae_mean"],
                "coverage_80_mean": row["coverage_80_mean"],
                "coverage_90_mean": row["coverage_90_mean"],
                "calibration_error_mean": row["calibration_error_mean"],
                "automatic_promotion": False,
            }
        )
    return pd.DataFrame(rows)


from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .ensemble_conformal_contract import (
    CertificationError,
    ConformalConfig,
    TemporalPartition,
)


class IntervalMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    lower_quantile: float
    upper_quantile: float
    nominal_coverage: float = Field(ge=0.0, le=1.0)
    empirical_coverage: float = Field(ge=0.0, le=1.0)
    coverage_gap: float
    mean_width: float = Field(ge=0.0)
    median_width: float = Field(ge=0.0)
    per_position_coverage: tuple[float, ...]
    all_position_coverage: float = Field(ge=0.0, le=1.0)


class ConformalCertification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    public_name: str
    quantiles: tuple[float, ...]
    non_crossing: bool
    median_base_parity: bool | None
    interval_metrics: tuple[IntervalMetric, ...]
    calibration_indices: tuple[int, ...]
    evaluation_indices: tuple[int, ...]


def _as_position_horizon(values: np.ndarray | Sequence[Sequence[float]]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 2 or not np.isfinite(array).all():
        raise CertificationError("expected finite position x horizon values")
    return array


def compute_interval_metrics(
    actual: np.ndarray | Sequence[Sequence[float]],
    lower: np.ndarray | Sequence[Sequence[float]],
    upper: np.ndarray | Sequence[Sequence[float]],
    *,
    lower_quantile: float,
    upper_quantile: float,
) -> IntervalMetric:
    y_true = _as_position_horizon(actual)
    low = _as_position_horizon(lower)
    high = _as_position_horizon(upper)
    if y_true.shape != low.shape or y_true.shape != high.shape:
        raise CertificationError("interval and actual shapes differ")
    if np.any(low > high):
        raise CertificationError("interval lower bound exceeds upper bound")
    covered = (y_true >= low) & (y_true <= high)
    widths = high - low
    nominal = float(upper_quantile - lower_quantile)
    empirical = float(covered.mean())
    return IntervalMetric(
        lower_quantile=lower_quantile,
        upper_quantile=upper_quantile,
        nominal_coverage=nominal,
        empirical_coverage=empirical,
        coverage_gap=empirical - nominal,
        mean_width=float(widths.mean()),
        median_width=float(np.median(widths)),
        per_position_coverage=tuple(float(value) for value in covered.mean(axis=1)),
        all_position_coverage=float(covered.all(axis=0).mean()),
    )


def certify_conformal_quantiles(
    config: ConformalConfig,
    partition: TemporalPartition,
    actual: np.ndarray | Sequence[Sequence[float]],
    quantile_predictions: Mapping[float, np.ndarray],
    *,
    base_median_prediction: np.ndarray | None = None,
    atol: float = 1e-12,
) -> ConformalCertification:
    expected = tuple(config.quantiles)
    observed_keys = tuple(sorted(float(key) for key in quantile_predictions))
    if observed_keys != expected:
        raise CertificationError("observed quantile keys differ from requested quantiles")
    arrays = [_as_position_horizon(quantile_predictions[key]) for key in expected]
    if len({array.shape for array in arrays}) != 1:
        raise CertificationError("quantile prediction shapes differ")
    stacked = np.stack(arrays, axis=0)
    if np.any(np.diff(stacked, axis=0) < -atol):
        raise CertificationError("quantile predictions cross")
    median_index = expected.index(0.5)
    median_parity: bool | None = None
    if config.require_median_base_parity:
        if base_median_prediction is None:
            raise CertificationError("base median prediction evidence is required")
        base = _as_position_horizon(base_median_prediction)
        if base.shape != arrays[median_index].shape:
            raise CertificationError("base median shape differs from conformal median")
        median_parity = bool(np.allclose(base, arrays[median_index], atol=atol, rtol=0.0))
        if not median_parity:
            raise CertificationError("conformal median differs from base median")
    intervals: list[IntervalMetric] = []
    half = len(expected) // 2
    for lower_q, upper_q in zip(expected[:half], reversed(expected[half + 1 :]), strict=True):
        intervals.append(
            compute_interval_metrics(
                actual,
                quantile_predictions[lower_q],
                quantile_predictions[upper_q],
                lower_quantile=lower_q,
                upper_quantile=upper_q,
            )
        )
    calibration_indices = tuple(
        range(partition.calibration_start, partition.calibration_end, config.cal_stride)
    )
    if config.cal_length is not None:
        calibration_indices = calibration_indices[-config.cal_length :]
    evaluation_indices = tuple(range(partition.evaluation_start, partition.evaluation_end))
    if set(calibration_indices) & set(evaluation_indices):
        raise CertificationError("calibration and evaluation indices overlap")
    return ConformalCertification(
        public_name=config.public_name,
        quantiles=expected,
        non_crossing=True,
        median_base_parity=median_parity,
        interval_metrics=tuple(intervals),
        calibration_indices=calibration_indices,
        evaluation_indices=evaluation_indices,
    )

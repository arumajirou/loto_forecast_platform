from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
MODEL_ID = "pp-multinomial-dglm"


def _softmax_reference(logits: FloatArray) -> FloatArray:
    values = np.concatenate([np.asarray(logits, dtype=np.float64), np.zeros(1)])
    values -= float(np.max(values))
    weights = np.exp(values)
    return (weights / weights.sum()).astype(np.float64)


def _ensure_psd(matrix: FloatArray, floor: float) -> tuple[FloatArray, float]:
    symmetric = 0.5 * (matrix + matrix.T)
    eigenvalues = np.linalg.eigvalsh(symmetric)
    minimum = float(eigenvalues.min())
    jitter = max(0.0, float(floor) - minimum)
    if jitter:
        symmetric = symmetric + np.eye(symmetric.shape[0], dtype=np.float64) * jitter
    if not np.isfinite(symmetric).all():
        raise ValueError("DGLM_FILTER_DIVERGED: covariance contains non-finite values")
    return symmetric.astype(np.float64), jitter


def _block_diagonal(matrix: FloatArray, blocks: int) -> FloatArray:
    rows, columns = matrix.shape
    output = np.zeros((rows * blocks, columns * blocks), dtype=np.float64)
    for index in range(blocks):
        left = index * rows
        top = index * columns
        output[left : left + rows, top : top + columns] = matrix
    return output


def _state_structure(
    *, include_trend: bool, seasonal_periods: tuple[float, ...], exogenous_dim: int
) -> tuple[tuple[str, ...], FloatArray]:
    names = ["local_level"]
    if include_trend:
        names.append("local_trend")
    for period in seasonal_periods:
        names.extend((f"seasonal_sin_{period:g}", f"seasonal_cos_{period:g}"))
    names.extend(f"exogenous_{index}" for index in range(exogenous_dim))
    evolution = np.eye(len(names), dtype=np.float64)
    if include_trend:
        evolution[0, 1] = 1.0
    return tuple(names), evolution


def _feature_vector(
    *,
    step: int,
    include_trend: bool,
    seasonal_periods: tuple[float, ...],
    exogenous: FloatArray | None,
) -> FloatArray:
    values = [1.0]
    if include_trend:
        values.append(0.0)
    for period in seasonal_periods:
        angle = 2.0 * np.pi * float(step) / float(period)
        values.extend((float(np.sin(angle)), float(np.cos(angle))))
    if exogenous is not None:
        values.extend(float(item) for item in exogenous)
    return np.asarray(values, dtype=np.float64)


def _validate_observations(y: np.ndarray, classes: int) -> FloatArray:
    values = np.asarray(y, dtype=np.float64)
    if values.ndim == 1:
        values = values[:, None]
    if values.ndim != 2 or values.shape[0] < 1 or values.shape[1] < 1:
        raise ValueError("multinomial DGLM observations must have shape (time, position)")
    finite = values[np.isfinite(values)]
    if finite.size and (np.any(finite < 0) or np.any(finite >= classes)):
        raise ValueError("multinomial DGLM observations contain an out-of-range category")
    if finite.size and not np.allclose(finite, np.round(finite)):
        raise ValueError("multinomial DGLM observations must be integer categories or NaN")
    return values


def _validate_exogenous(exogenous: np.ndarray | None, rows: int) -> FloatArray | None:
    if exogenous is None:
        return None
    values = np.asarray(exogenous, dtype=np.float64)
    if values.ndim == 1:
        values = values[:, None]
    if values.ndim != 2 or values.shape[0] != rows:
        raise ValueError("exogenous must have shape (time, feature)")
    if not np.isfinite(values).all():
        raise ValueError("exogenous contains non-finite values")
    return values

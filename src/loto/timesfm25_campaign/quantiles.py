from __future__ import annotations

import numpy as np

from loto.adapters.timesfm25.contracts import QUANTILE_KEYS


def split_native_outputs(
    point_forecast: np.ndarray,
    full_forecast: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    point = np.asarray(point_forecast, dtype=float)
    full = np.asarray(full_forecast, dtype=float)
    if point.ndim != 2:
        raise ValueError(f"point forecast must have shape [series,horizon], got {point.shape}")
    if full.ndim != 3 or full.shape[:2] != point.shape or full.shape[2] != 10:
        raise ValueError(
            "full forecast must have shape [series,horizon,10] aligned with point forecast"
        )
    if not np.isfinite(point).all() or not np.isfinite(full).all():
        raise ValueError("TimesFM output contains NaN or Inf")
    mean = full[:, :, 0]
    quantiles = {key: full[:, :, index] for index, key in enumerate(QUANTILE_KEYS, start=1)}
    qstack = np.stack([quantiles[key] for key in QUANTILE_KEYS], axis=-1)
    if np.any(np.diff(qstack, axis=-1) < 0):
        raise ValueError("quantile crossing detected")
    if not np.allclose(point, quantiles["0.5"], rtol=1e-5, atol=1e-5):
        raise ValueError("native point forecast does not equal q0.5")
    return point, mean, quantiles

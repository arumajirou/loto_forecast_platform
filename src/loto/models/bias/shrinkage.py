from __future__ import annotations

import numpy as np


def _normalise_rows(probabilities: np.ndarray, name: str) -> np.ndarray:
    values = np.asarray(probabilities, dtype=float)
    if values.ndim != 2 or not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError(f"{name} must be a finite non-negative 2-D matrix")
    totals = values.sum(axis=1)
    if np.any(totals <= 0):
        raise ValueError(f"{name} rows must contain positive mass")
    return values / totals[:, None]


def mix_positional_distributions(
    null_probabilities: np.ndarray,
    bias_probabilities: np.ndarray,
    *,
    alpha: float,
) -> np.ndarray:
    """Explicitly mix null and bias positional distributions.

    ``alpha`` is supplied by the caller and must be fixed from pre-target evidence. This function
    intentionally does not estimate alpha from the target window or infer that bias evidence
    exists.
    """
    if not np.isfinite(alpha) or not 0.0 <= alpha <= 1.0:
        raise ValueError("alpha must be finite and in [0, 1]")
    null = _normalise_rows(null_probabilities, "null_probabilities")
    bias = _normalise_rows(bias_probabilities, "bias_probabilities")
    if null.shape != bias.shape:
        raise ValueError("null and bias probability shapes must match")
    mixed = (1.0 - alpha) * null + alpha * bias
    return mixed / mixed.sum(axis=1, keepdims=True)

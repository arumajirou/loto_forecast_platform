from __future__ import annotations

import numpy as np


def hit1_utility(probabilities: np.ndarray) -> np.ndarray:
    """Return boundary-aware P(|Y-k| <= 1) for every candidate k."""
    probs = np.asarray(probabilities, dtype=float)
    left = np.pad(probs[..., :-1], [(0, 0)] * (probs.ndim - 1) + [(1, 0)])
    right = np.pad(probs[..., 1:], [(0, 0)] * (probs.ndim - 1) + [(0, 1)])
    return left + probs + right


def expected_squared_error(probabilities: np.ndarray) -> np.ndarray:
    probs = np.asarray(probabilities, dtype=float)
    candidates = np.arange(probs.shape[-1], dtype=float)
    true_values = candidates.copy()
    squared = (true_values[:, None] - candidates[None, :]) ** 2
    return np.einsum("...i,ij->...j", probs, squared)


def choose_points(
    probabilities: np.ndarray,
    *,
    model_id: str,
    value_min: int,
    lambda_mse: float = 0.02,
) -> np.ndarray:
    probs = np.asarray(probabilities, dtype=float)
    if "posterior-utility-hit1-mse" in model_id:
        score = hit1_utility(probs) - lambda_mse * expected_squared_error(probs)
    elif "posterior-utility-hit1" in model_id:
        score = hit1_utility(probs)
    else:
        score = probs
    return np.argmax(score, axis=-1).astype(int) + int(value_min)

from __future__ import annotations

import numpy as np


def brier_score(targets: np.ndarray, probabilities: np.ndarray) -> float:
    y = np.asarray(targets, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    if y.shape != p.shape:
        raise ValueError("shape mismatch")
    return float(np.mean((p - y) ** 2))


def log_loss(targets: np.ndarray, probabilities: np.ndarray) -> float:
    y = np.asarray(targets, dtype=float)
    p = np.clip(np.asarray(probabilities, dtype=float), 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def expected_calibration_error(
    targets: np.ndarray, probabilities: np.ndarray, bins: int = 10
) -> float:
    y = np.asarray(targets, dtype=float).ravel()
    p = np.asarray(probabilities, dtype=float).ravel()
    edges = np.linspace(0, 1, bins + 1)
    len(y)
    ece = 0.0
    for i in range(bins):
        mask = (p >= edges[i]) & (p < edges[i + 1] if i < bins - 1 else p <= edges[i + 1])
        if mask.any():
            ece += mask.mean() * abs(float(y[mask].mean() - p[mask].mean()))
    return float(ece)


def evaluate_draws(actual: np.ndarray, predicted: np.ndarray, tau: int = 1) -> dict[str, float]:
    actual = np.asarray(actual, dtype=int)
    predicted = np.asarray(predicted, dtype=int)
    if actual.shape != predicted.shape or actual.ndim != 2 or actual.shape[1] != 7:
        raise ValueError("actual and predicted must have shape (n,7)")
    hits = np.array(
        [len(set(a) & set(p)) for a, p in zip(actual, predicted, strict=False)], dtype=float
    )
    errors = np.abs(actual - predicted)
    return {
        "mean_hits_at_7": float(hits.mean()),
        "position_mae": float(errors.mean()),
        "position_mse": float((errors**2).mean()),
        "within_1_rate": float((errors <= tau).mean()),
    }


def paired_draw_bootstrap(
    scores_a: np.ndarray, scores_b: np.ndarray, n_boot: int = 10000, seed: int = 0
) -> dict:
    a = np.asarray(scores_a, dtype=float)
    b = np.asarray(scores_b, dtype=float)
    if a.shape != b.shape or a.ndim != 1:
        raise ValueError("paired draw scores must be 1-D and aligned")
    diff_by_draw = a - b
    rng = np.random.default_rng(seed)
    n = len(a)
    idx = rng.integers(0, n, size=(n_boot, n))
    boot = diff_by_draw[idx].mean(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {
        "n_draws": n,
        "diff": float(diff_by_draw.mean()),
        "ci95": [float(lo), float(hi)],
        "probability_positive": float((boot > 0).mean()),
    }

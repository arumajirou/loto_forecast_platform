from __future__ import annotations

import numpy as np

from loto.game.geometry import GameGeometry, geometry_for


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


def evaluate_outcomes(
    actual: np.ndarray,
    predicted: np.ndarray,
    geometry: GameGeometry | str,
    tau: int = 1,
) -> dict[str, float]:
    """Geometry-general draw evaluation for every canonical game family.

    ``mean_hits`` follows game semantics: select-family games use set overlap, while digit games
    count exact positional matches so repeated digits and digit order are preserved.
    """
    if tau < 0:
        raise ValueError("tau must be >= 0")
    resolved = geometry_for(geometry) if isinstance(geometry, str) else geometry
    actual_array = np.asarray(actual, dtype=int)
    predicted_array = np.asarray(predicted, dtype=int)
    expected_width = resolved.positions
    if (
        actual_array.shape != predicted_array.shape
        or actual_array.ndim != 2
        or actual_array.shape[1] != expected_width
    ):
        raise ValueError(
            f"actual and predicted must have shape (n,{expected_width}) for game={resolved.key!r}"
        )
    for row in actual_array:
        resolved.validate_outcome(row.tolist())
    for row in predicted_array:
        resolved.validate_outcome(row.tolist())

    if resolved.family == "digits":
        hits = np.sum(actual_array == predicted_array, axis=1, dtype=float)
    else:
        hits = np.array(
            [
                len(set(actual_row) & set(predicted_row))
                for actual_row, predicted_row in zip(
                    actual_array,
                    predicted_array,
                    strict=True,
                )
            ],
            dtype=float,
        )
    errors = np.abs(actual_array - predicted_array)
    within = errors <= tau
    return {
        "mean_hits": float(hits.mean()),
        "position_mae": float(errors.mean()),
        "position_mse": float((errors**2).mean()),
        "position_rmse": float(np.sqrt((errors**2).mean())),
        "within_tau_rate": float(within.mean()),
        "all_positions_within_tau_rate": float(within.all(axis=1).mean()),
    }


def evaluate_draws(actual: np.ndarray, predicted: np.ndarray, tau: int = 1) -> dict[str, float]:
    """Backward-compatible Loto7 wrapper around :func:`evaluate_outcomes`."""
    result = evaluate_outcomes(actual, predicted, geometry_for("loto7"), tau=tau)
    return {
        "mean_hits_at_7": result["mean_hits"],
        "position_mae": result["position_mae"],
        "position_mse": result["position_mse"],
        "within_1_rate": result["within_tau_rate"],
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

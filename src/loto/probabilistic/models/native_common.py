from __future__ import annotations

import math
from typing import Any

import numpy as np


def bounded_training_data(y: np.ndarray, max_rows: int) -> np.ndarray:
    values = np.asarray(y)
    if values.ndim == 1:
        values = values[:, None]
    return values[-min(len(values), max_rows) :]


def time_features(n: int, *, degree: int = 2, harmonics: int = 1) -> tuple[np.ndarray, np.ndarray]:
    if n < 1:
        raise ValueError("n must be positive")
    t = np.linspace(-1.0, 1.0, n, dtype=float)
    next_t = 1.0 + (2.0 / max(n - 1, 1))
    columns = [np.ones(n), t]
    next_columns = [1.0, next_t]
    for power in range(2, degree + 1):
        columns.append(t**power)
        next_columns.append(next_t**power)
    for harmonic in range(1, harmonics + 1):
        columns.extend(
            [
                np.sin(math.pi * harmonic * (t + 1.0)),
                np.cos(math.pi * harmonic * (t + 1.0)),
            ]
        )
        next_columns.extend(
            [
                math.sin(math.pi * harmonic * (next_t + 1.0)),
                math.cos(math.pi * harmonic * (next_t + 1.0)),
            ]
        )
    return np.column_stack(columns).astype(float), np.asarray(next_columns, dtype=float)


def lag_features(y: np.ndarray, classes: int) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(y, dtype=float)
    if values.ndim == 1:
        values = values[:, None]
    scale = max(classes - 1, 1)
    normalized = values / scale
    lag = np.vstack([normalized[:1], normalized[:-1]])
    next_lag = normalized[-1]
    return lag, next_lag


def categorical_design(y: np.ndarray, classes: int, *, degree: int = 2, harmonics: int = 1) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(y)
    if values.ndim == 1:
        values = values[:, None]
    base, next_base = time_features(len(values), degree=degree, harmonics=harmonics)
    lag, next_lag = lag_features(values, classes)
    # Shared temporal features; model coefficients remain position-specific.  The mean lag
    # gives a compact leakage-safe autoregressive covariate available at forecast time.
    X = np.column_stack([base, lag.mean(axis=1)])
    X_next = np.concatenate([next_base, [float(next_lag.mean())]])
    return X.astype(float), X_next.astype(float)


def categorical_counts(y: np.ndarray, classes: int, weights: np.ndarray | None = None) -> np.ndarray:
    values = np.asarray(y, dtype=int)
    if values.ndim == 1:
        values = values[:, None]
    row_weights = np.ones(len(values), dtype=float) if weights is None else np.asarray(weights, dtype=float)
    counts = np.zeros((values.shape[1], classes), dtype=float)
    for position in range(values.shape[1]):
        counts[position] = np.bincount(
            values[:, position], weights=row_weights, minlength=classes
        )
    return counts


def empirical_probabilities(
    y: np.ndarray, classes: int, *, prior: float = 1.0, window: int | None = None, discount: float | None = None
) -> np.ndarray:
    values = np.asarray(y, dtype=int)
    if window is not None:
        values = values[-min(window, len(values)) :]
    weights = None
    if discount is not None:
        age = np.arange(len(values) - 1, -1, -1, dtype=float)
        weights = np.power(discount, age)
    counts = categorical_counts(values, classes, weights)
    alpha = counts + float(prior)
    return alpha / alpha.sum(axis=-1, keepdims=True)


def base_probability_bank(y: np.ndarray, classes: int, *, prior: float, window: int, discount: float) -> np.ndarray:
    values = np.asarray(y, dtype=int)
    if values.ndim == 1:
        values = values[:, None]
    positions = values.shape[1]
    uniform = np.full((positions, classes), 1.0 / classes)
    full = empirical_probabilities(values, classes, prior=prior)
    recent = empirical_probabilities(values, classes, prior=prior, window=window)
    discounted = empirical_probabilities(values, classes, prior=prior, discount=discount)
    return np.stack([uniform, full, recent, discounted], axis=0)


def gaussian_kernel_probabilities(location_draws: np.ndarray, classes: int, *, scale: float = 1.0) -> np.ndarray:
    locations = np.asarray(location_draws, dtype=float)
    if locations.ndim == 1:
        locations = locations[:, None]
    grid = np.arange(classes, dtype=float)
    logits = -0.5 * ((grid[None, None, :] - locations[:, :, None]) / max(scale, 1e-6)) ** 2
    logits -= logits.max(axis=-1, keepdims=True)
    probs = np.exp(logits)
    probs /= probs.sum(axis=-1, keepdims=True)
    return probs


def softmax_numpy(logits: np.ndarray, axis: int = -1) -> np.ndarray:
    values = np.asarray(logits, dtype=float)
    values = values - np.max(values, axis=axis, keepdims=True)
    output = np.exp(values)
    return output / np.maximum(output.sum(axis=axis, keepdims=True), 1e-15)


def profile_settings(config: Any, profile: Any | None) -> dict[str, Any]:
    defaults = dict(getattr(profile, "default", {}) or {})
    profile_id = getattr(profile, "profile_id", None)
    return {
        "profile_id": profile_id,
        "algorithm": getattr(profile, "algorithm", "native-default") if profile else "native-default",
        "chains": min(int(defaults.get("chains", config.native_chains)), config.native_chains),
        "draws": min(
            int(defaults.get("draws", defaults.get("samples", defaults.get("iter_sampling", config.native_draws)))),
            config.native_draws,
        ),
        "warmup": min(
            int(defaults.get("tune", defaults.get("warmup", defaults.get("iter_warmup", config.native_warmup)))),
            config.native_warmup,
        ),
        "steps": min(int(defaults.get("steps", defaults.get("iter", config.native_svi_steps))), config.native_svi_steps),
        "particles": min(int(defaults.get("particles", config.native_particles)), config.native_particles),
        "target_accept": max(
            float(defaults.get("target_accept", defaults.get("adapt_delta", 0.9))),
            float(config.native_target_accept),
        ),
        "posterior_draws": min(int(defaults.get("posterior_draws", config.native_draws)), config.native_draws),
    }

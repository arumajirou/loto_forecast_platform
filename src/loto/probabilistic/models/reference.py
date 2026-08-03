from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from loto.game.geometry import GameGeometry
from loto.probabilistic.contracts import ProbabilisticModelSpec, ProbabilisticRunConfig


@dataclass
class ReferencePosterior:
    model_id: str
    family: str
    strategy: str
    target_mode: str
    game: str
    alpha: np.ndarray
    metadata: dict[str, Any]

    @property
    def probabilities(self) -> np.ndarray:
        denom = self.alpha.sum(axis=-1, keepdims=True)
        return self.alpha / np.maximum(denom, 1e-12)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "family": self.family,
            "strategy": self.strategy,
            "target_mode": self.target_mode,
            "game": self.game,
            "alpha": self.alpha.tolist(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReferencePosterior":
        return cls(
            model_id=str(payload["model_id"]),
            family=str(payload["family"]),
            strategy=str(payload["strategy"]),
            target_mode=str(payload["target_mode"]),
            game=str(payload["game"]),
            alpha=np.asarray(payload["alpha"], dtype=float),
            metadata=dict(payload.get("metadata") or {}),
        )


def _categorical_counts(y: np.ndarray, classes: int, weights: np.ndarray | None = None) -> np.ndarray:
    if y.ndim == 1:
        y = y[:, None]
    counts = np.zeros((y.shape[1], classes), dtype=float)
    row_weights = np.ones(y.shape[0], dtype=float) if weights is None else np.asarray(weights, dtype=float)
    for position in range(y.shape[1]):
        counts[position] = np.bincount(y[:, position], weights=row_weights, minlength=classes)
    return counts


def _incidence_counts(y: np.ndarray, classes: int, weights: np.ndarray | None = None) -> np.ndarray:
    row_weights = np.ones(y.shape[0], dtype=float) if weights is None else np.asarray(weights, dtype=float)
    if y.ndim == 1:
        y = y[:, None]
    counts = (y * row_weights[:, None]).sum(axis=0, dtype=float)
    # Represent candidate inclusion as a two-category posterior per candidate: absent/present.
    return np.stack([row_weights.sum() - counts, counts], axis=1)


def _empirical_alpha(counts: np.ndarray, base: float) -> float:
    probabilities = counts / np.maximum(counts.sum(axis=-1, keepdims=True), 1.0)
    variance = float(np.var(probabilities))
    concentration = 1.0 / max(variance * probabilities.shape[-1], 1e-3)
    return float(np.clip(0.5 * concentration, 0.05, max(50.0, base)))


def _transition_counts(y: np.ndarray, classes: int, prior: float) -> np.ndarray:
    if y.ndim == 1:
        y = y[:, None]
    alpha = np.full((y.shape[1], classes), prior, dtype=float)
    if len(y) < 2:
        return alpha + _categorical_counts(y, classes)
    for pos in range(y.shape[1]):
        previous = int(y[-1, pos])
        transitions = np.zeros(classes, dtype=float)
        for index in range(1, len(y)):
            distance = abs(int(y[index - 1, pos]) - previous)
            weight = math.exp(-0.45 * distance) * (0.995 ** (len(y) - 1 - index))
            transitions[int(y[index, pos])] += weight
        alpha[pos] += transitions
    return alpha


def _dynamic_weights(n: int, model_id: str, discount: float, window: int) -> np.ndarray:
    age = np.arange(n - 1, -1, -1, dtype=float)
    if "seasonal" in model_id:
        return np.maximum(0.05, 1.0 + 0.5 * np.cos(2 * np.pi * age / max(5, window)))
    if "changepoint" in model_id:
        split = max(1, n // (3 if "multiple" in model_id else 2))
        weights = np.full(n, 0.2)
        weights[-split:] = 1.0
        return weights
    if any(token in model_id for token in ("hmm", "switching", "hsmm")):
        weights = np.power(discount, age)
        if n >= 3:
            recent_center = np.mean(np.arange(n)[-min(window, n):])
            weights *= 0.75 + 0.25 * (np.arange(n) >= recent_center)
        return weights
    return np.power(discount, age)


def _mixture_alpha(y: np.ndarray, classes: int, prior: float, window: int, model_id: str) -> np.ndarray:
    full = _categorical_counts(y, classes)
    recent = _categorical_counts(y[-min(window, len(y)):], classes)
    transition = _transition_counts(y, classes, prior=0.0)
    if "mixture-of-experts" in model_id:
        weights = (0.25, 0.45, 0.30)
    elif "sticky" in model_id:
        weights = (0.15, 0.65, 0.20)
    elif "changepoint" in model_id:
        weights = (0.10, 0.75, 0.15)
    else:
        weights = (0.40, 0.40, 0.20)
    return prior + weights[0] * full + weights[1] * recent + weights[2] * transition


def _sequence_bootstrap_alpha(
    y: np.ndarray, classes: int, prior: float, window: int, model_id: str
) -> np.ndarray:
    # Dependency-light reference for the deep-PPL catalog. It preserves sequential context,
    # posterior uncertainty and model-specific receptive fields. Native Pyro/TFP execution is
    # exposed separately and is never silently claimed by this reference path.
    receptive = window
    if "transformer" in model_id:
        receptive = max(window * 3, 60)
    elif any(token in model_id for token in ("gru", "lstm", "rnn", "markov")):
        receptive = max(window * 2, 40)
    elif "tcn" in model_id:
        receptive = max(window, 32)
    recent = y[-min(receptive, len(y)):]
    recency = np.linspace(0.25, 1.0, len(recent))
    alpha = prior + _categorical_counts(recent, classes, recency)
    alpha += 0.35 * _transition_counts(y, classes, prior=0.0)
    return alpha


def fit_reference(
    spec: ProbabilisticModelSpec,
    *,
    y: np.ndarray,
    classes: int,
    target_mode: str,
    geometry: GameGeometry,
    config: ProbabilisticRunConfig,
    seed: int,
) -> ReferencePosterior:
    if len(y) < 2:
        raise ValueError("at least two training rows are required")
    prior = float(config.prior_concentration)
    strategy = spec.reference_strategy
    metadata: dict[str, Any] = {
        "reference_backend": "builtin",
        "native_backends": list(spec.backends),
        "training_rows": int(len(y)),
        "seed": int(seed),
        "prior_concentration": prior,
        "rolling_window": config.rolling_window,
        "discount_factor": config.discount_factor,
        "reference_semantics": (
            "dependency-light executable analogue; use a declared native backend for "
            "full MCMC/SVI semantics"
        ),
    }
    inclusion_mode = target_mode in {"select_candidate_inclusion", "select_position_inclusion"}
    if target_mode == "window_count" and y.ndim == 2 and y.shape[1] == classes:
        intensity = y.sum(axis=0, dtype=float) + prior
        if "zero-inflated" in spec.model_id or "hurdle" in spec.model_id:
            zero_rate = np.mean(y == 0, axis=0)
            intensity *= np.maximum(0.1, 1.0 - 0.5 * zero_rate)
        if "negative-binomial" in spec.model_id or "overdispersed" in spec.model_id:
            intensity += np.sqrt(np.maximum(np.var(y, axis=0), 0.0))
        alpha = intensity[None, :]
        metadata["window_count_reference"] = True
    elif inclusion_mode and y.ndim == 2 and y.shape[1] == classes:
        successes = y.sum(axis=0, dtype=float)
        alpha = (successes + prior)[None, :]
        metadata["inclusion_trials"] = int(len(y))
    elif strategy == "uniform":
        positions = y.shape[1] if y.ndim > 1 else 1
        alpha = np.full((positions, classes), prior, dtype=float)
    elif strategy == "dirichlet":
        alpha = prior + _categorical_counts(y, classes)
    elif strategy == "rolling_dirichlet":
        recent = y[-min(config.rolling_window, len(y)):]
        alpha = prior + _categorical_counts(recent, classes)
    elif strategy == "discounted_dirichlet":
        weights = _dynamic_weights(len(y), spec.model_id, config.discount_factor, config.rolling_window)
        alpha = prior + _categorical_counts(y, classes, weights)
    elif strategy == "empirical_bayes":
        counts = _categorical_counts(y, classes)
        estimated = _empirical_alpha(counts, prior)
        alpha = estimated + counts
        metadata["estimated_concentration"] = estimated
    elif strategy == "hierarchical_pooling":
        local = _categorical_counts(y, classes)
        global_counts = local.sum(axis=0, keepdims=True)
        global_probs = global_counts / np.maximum(global_counts.sum(), 1.0)
        pooling = 0.35 if "digits" in spec.model_id else 0.50
        alpha = prior + (1.0 - pooling) * local + pooling * local.sum(axis=1, keepdims=True) * global_probs
        metadata["pooling_weight"] = pooling
    elif strategy == "context_transition":
        alpha = prior + _transition_counts(y, classes, prior=0.0)
        if spec.family == "ordinal":
            kernel = np.exp(-0.5 * ((np.arange(classes)[:, None] - np.arange(classes)[None, :]) / 1.5) ** 2)
            alpha = alpha @ kernel
        elif spec.family == "semi_parametric":
            alpha += 0.25 * _categorical_counts(y[-min(50, len(y)):], classes)
        elif spec.family == "gaussian_process":
            weights = np.exp(-0.5 * (np.arange(len(y) - 1, -1, -1) / max(10.0, config.rolling_window)) ** 2)
            alpha += 0.5 * _categorical_counts(y, classes, weights)
        elif spec.family == "tree_bayesian":
            alpha += 0.6 * _categorical_counts(y[-min(config.rolling_window, len(y)):], classes)
    elif strategy == "dynamic_context":
        weights = _dynamic_weights(len(y), spec.model_id, config.discount_factor, config.rolling_window)
        alpha = prior + _categorical_counts(y, classes, weights)
        alpha += 0.25 * _transition_counts(y, classes, prior=0.0)
    elif strategy == "count_posterior":
        if y.ndim == 2 and y.shape[1] == classes and np.all(y >= 0):
            # Convert count/inclusion intensity to a simplex for common downstream evaluation.
            intensity = y.sum(axis=0, dtype=float) + prior
            if "zero-inflated" in spec.model_id or "hurdle" in spec.model_id:
                zero_rate = np.mean(y == 0, axis=0)
                intensity *= np.maximum(0.1, 1.0 - 0.5 * zero_rate)
            if "negative-binomial" in spec.model_id or "overdispersed" in spec.model_id:
                variance = np.var(y, axis=0)
                intensity += np.sqrt(np.maximum(variance, 0.0))
            alpha = intensity[None, :]
        else:
            alpha = prior + _categorical_counts(y, classes)
    elif strategy == "mixture_context":
        alpha = _mixture_alpha(y, classes, prior, config.rolling_window, spec.model_id)
    elif strategy == "sequence_bootstrap":
        alpha = _sequence_bootstrap_alpha(y, classes, prior, config.rolling_window, spec.model_id)
    elif strategy == "ensemble_reference":
        a = prior + _categorical_counts(y, classes)
        b = prior + _categorical_counts(y[-min(config.rolling_window, len(y)):], classes)
        c = prior + _transition_counts(y, classes, prior=0.0)
        alpha = (a + b + c) / 3.0
    elif strategy == "calibration_reference":
        alpha = prior + _categorical_counts(y, classes)
        temperature = 1.25 if "temperature" in spec.model_id else 1.10
        probs = alpha / alpha.sum(axis=-1, keepdims=True)
        probs = np.power(np.maximum(probs, 1e-12), 1.0 / temperature)
        probs /= probs.sum(axis=-1, keepdims=True)
        alpha = probs * max(float(len(y)), classes)
        metadata["temperature"] = temperature
    elif strategy == "decision_reference":
        alpha = prior + _categorical_counts(y, classes)
    else:
        alpha = prior + _categorical_counts(y, classes)
    alpha = np.asarray(alpha, dtype=float)
    if alpha.ndim == 1:
        alpha = alpha[None, :]
    if not np.isfinite(alpha).all() or np.any(alpha <= 0):
        raise ValueError(f"invalid posterior alpha for {spec.model_id}")
    return ReferencePosterior(
        model_id=spec.model_id,
        family=spec.family,
        strategy=strategy,
        target_mode=target_mode,
        game=geometry.key,
        alpha=alpha,
        metadata=metadata,
    )


def posterior_draws(
    posterior: ReferencePosterior, *, draws: int, seed: int
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    output = np.empty((draws, posterior.alpha.shape[0], posterior.alpha.shape[1]), dtype=float)
    for position, alpha in enumerate(posterior.alpha):
        output[:, position, :] = rng.dirichlet(alpha, size=draws)
    return output

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from loto.game.geometry import GameGeometry


def _elementary_suffix(weights: np.ndarray, k: int) -> np.ndarray:
    """Suffix elementary-symmetric sums for product-weight fixed-k sampling."""
    n = len(weights)
    table = np.zeros((n + 1, k + 1), dtype=float)
    table[:, 0] = 1.0
    for index in range(n - 1, -1, -1):
        max_r = min(k, n - index)
        for r in range(1, max_r + 1):
            table[index, r] = table[index + 1, r] + weights[index] * table[index + 1, r - 1]
    return table


@dataclass(frozen=True)
class WeightedSubsetBiasModel:
    """Product-weight fixed-k subset challenger estimated from smoothed inclusion odds.

    This is an unordered subset model. It deliberately does not interpret the sorted published
    numbers as physical extraction order.
    """

    game: str
    weights: tuple[float, ...]
    n_observations: int
    prior_strength: float
    model_id: str = "product-weight-fixed-k-bias-v1"

    def _weights(self, geometry: GameGeometry) -> np.ndarray:
        if geometry.key != self.game or geometry.family != "select":
            raise ValueError("model/geometry mismatch")
        values = np.asarray(self.weights, dtype=float)
        if values.shape != (geometry.universe_size,) or np.any(values <= 0):
            raise ValueError("stored subset weights are invalid")
        return values

    def sample(
        self,
        geometry: GameGeometry,
        *,
        n_samples: int,
        seed: int,
    ) -> np.ndarray:
        """Sample exactly from ``P(S) ∝ product(w_i)`` for ``|S|=k``."""
        if n_samples < 1:
            raise ValueError("n_samples must be >= 1")
        weights = self._weights(geometry)
        suffix = _elementary_suffix(weights, geometry.positions)
        normalizer = suffix[0, geometry.positions]
        if not np.isfinite(normalizer) or normalizer <= 0:
            raise ValueError("subset normalizer is invalid")
        rng = np.random.default_rng(seed)
        output = np.empty((n_samples, geometry.positions), dtype=int)
        for sample_index in range(n_samples):
            selected: list[int] = []
            remaining = geometry.positions
            for index, weight in enumerate(weights):
                if remaining == 0:
                    break
                candidates_left = geometry.universe_size - index
                if candidates_left == remaining:
                    selected.extend(range(index, geometry.universe_size))
                    remaining = 0
                    break
                denominator = suffix[index, remaining]
                numerator = weight * suffix[index + 1, remaining - 1]
                include_probability = float(numerator / denominator)
                if rng.random() < include_probability:
                    selected.append(index)
                    remaining -= 1
            if remaining != 0 or len(selected) != geometry.positions:
                raise AssertionError("fixed-k sampler failed to select the required cardinality")
            values = np.asarray(selected, dtype=int) + geometry.value_min
            geometry.validate_outcome(values.tolist())
            output[sample_index] = values
        return output

    def positional_marginals(
        self,
        geometry: GameGeometry,
        *,
        n_samples: int = 10000,
        seed: int = 42,
    ) -> np.ndarray:
        """Monte-Carlo ordered-position marginals from the unordered fixed-k model."""
        samples = self.sample(geometry, n_samples=n_samples, seed=seed)
        probabilities = np.zeros((geometry.positions, geometry.universe_size), dtype=float)
        for position in range(geometry.positions):
            indexes = samples[:, position] - geometry.value_min
            counts = np.bincount(indexes, minlength=geometry.universe_size)
            probabilities[position] = counts / n_samples
        return probabilities


def fit_weighted_subset_bias(
    history: np.ndarray,
    geometry: GameGeometry,
    *,
    prior_strength: float = 20.0,
) -> WeightedSubsetBiasModel:
    """Fit smoothed inclusion odds for a product-weight fixed-k challenger.

    The fitted weights are a transparent empirical baseline, not an MLE claim. Formal adoption
    requires chronological OOF and comparison with the exact uniform fixed-k null.
    """
    if geometry.family != "select":
        raise ValueError("weighted subset bias model requires a select-family game")
    if not np.isfinite(prior_strength) or prior_strength <= 0:
        raise ValueError("prior_strength must be finite and > 0")
    values = np.asarray(history, dtype=int)
    if values.ndim != 2 or values.shape[1] != geometry.positions or len(values) < 1:
        raise ValueError(f"history must have shape (n,{geometry.positions}) with n >= 1")
    inclusion = np.zeros(geometry.universe_size, dtype=float)
    for row in values:
        geometry.validate_outcome(row.tolist())
        inclusion[row - geometry.value_min] += 1.0

    null_rate = geometry.positions / geometry.universe_size
    smoothed_rate = (inclusion + prior_strength * null_rate) / (len(values) + prior_strength)
    eps = 1e-9
    odds = np.clip(smoothed_rate, eps, 1 - eps) / np.clip(1 - smoothed_rate, eps, 1 - eps)
    # Only relative weights matter; center them to keep the symmetric-sum DP numerically stable.
    log_weights = np.log(odds)
    log_weights -= log_weights.mean()
    weights = np.exp(np.clip(log_weights, -20.0, 20.0))
    return WeightedSubsetBiasModel(
        game=geometry.key,
        weights=tuple(float(value) for value in weights),
        n_observations=len(values),
        prior_strength=float(prior_strength),
    )

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from loto.game.geometry import GameGeometry


@dataclass(frozen=True)
class DirichletCategoricalBiasModel:
    """Smoothed per-position categorical probabilities for digit-family research."""

    game: str
    probabilities: tuple[tuple[float, ...], ...]
    n_observations: int
    prior_strength: float
    decay: float | None
    model_id: str = "dirichlet-categorical-bias-v1"

    def predict_distribution(self, geometry: GameGeometry) -> np.ndarray:
        if geometry.key != self.game or geometry.family != "digits":
            raise ValueError("model/geometry mismatch")
        array = np.asarray(self.probabilities, dtype=float)
        expected = (geometry.positions, geometry.universe_size)
        if array.shape != expected:
            raise ValueError(f"stored distribution shape mismatch: expected {expected}, got {array.shape}")
        return array.copy()


def fit_dirichlet_categorical_bias(
    history: np.ndarray,
    geometry: GameGeometry,
    *,
    prior_strength: float = 10.0,
    decay: float | None = None,
) -> DirichletCategoricalBiasModel:
    """Fit a Train/history-only Dirichlet-smoothed categorical challenger.

    ``decay`` is an optional geometric weight in ``(0, 1]`` applied from newest to oldest. It is
    a result-affecting hyperparameter and must therefore be fixed inside the training protocol.
    """
    if geometry.family != "digits":
        raise ValueError("Dirichlet categorical bias model requires a digits-family game")
    if not np.isfinite(prior_strength) or prior_strength <= 0:
        raise ValueError("prior_strength must be finite and > 0")
    if decay is not None and (not np.isfinite(decay) or not 0.0 < decay <= 1.0):
        raise ValueError("decay must be in (0, 1]")
    values = np.asarray(history, dtype=int)
    if values.ndim != 2 or values.shape[1] != geometry.positions or len(values) < 1:
        raise ValueError(f"history must have shape (n,{geometry.positions}) with n >= 1")
    for row in values:
        geometry.validate_outcome(row.tolist())

    if decay is None:
        row_weights = np.ones(len(values), dtype=float)
    else:
        age = np.arange(len(values) - 1, -1, -1, dtype=float)
        row_weights = np.power(decay, age)

    prior_per_value = prior_strength / geometry.universe_size
    probabilities = np.zeros((geometry.positions, geometry.universe_size), dtype=float)
    for position in range(geometry.positions):
        counts = np.full(geometry.universe_size, prior_per_value, dtype=float)
        indexes = values[:, position] - geometry.value_min
        np.add.at(counts, indexes, row_weights)
        probabilities[position] = counts / counts.sum()

    return DirichletCategoricalBiasModel(
        game=geometry.key,
        probabilities=tuple(tuple(float(value) for value in row) for row in probabilities),
        n_observations=len(values),
        prior_strength=float(prior_strength),
        decay=decay,
    )

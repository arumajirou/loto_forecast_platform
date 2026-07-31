from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize


@dataclass
class NonNegativeEnsemble:
    max_weight: float = 0.60
    weights_: np.ndarray | None = None

    def fit(self, predictions: np.ndarray, targets: np.ndarray) -> NonNegativeEnsemble:
        """Fit OOF weights. predictions=(samples, models, outputs)."""
        values = np.asarray(predictions, dtype=float)
        y = np.asarray(targets, dtype=float)
        if values.ndim != 3 or values.shape[0] != y.shape[0] or values.shape[2] != y.shape[1]:
            raise ValueError("predictions must be (samples, models, outputs) matching targets")
        model_count = values.shape[1]
        if self.max_weight * model_count < 1.0:
            raise ValueError("max_weight is too low to permit weights summing to one")

        def loss(w):
            combined = np.einsum("smo,m->so", values, w)
            return float(np.mean((combined - y) ** 2))

        result = minimize(
            loss,
            np.full(model_count, 1 / model_count),
            method="SLSQP",
            bounds=[(0.0, self.max_weight)] * model_count,
            constraints=[{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}],
        )
        if not result.success:
            self.weights_ = np.full(model_count, 1 / model_count)
        else:
            self.weights_ = np.asarray(result.x, dtype=float)
        return self

    def predict(self, predictions: np.ndarray) -> np.ndarray:
        if self.weights_ is None:
            raise RuntimeError("ensemble is not fitted")
        values = np.asarray(predictions, dtype=float)
        return np.einsum("smo,m->so", values, self.weights_)

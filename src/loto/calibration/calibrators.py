from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression


class PlattCalibrator:
    def __init__(self):
        self.model = LogisticRegression(C=1e6, max_iter=1000)
        self.fitted = False

    def fit(self, probabilities: np.ndarray, targets: np.ndarray) -> "PlattCalibrator":
        p = np.clip(np.asarray(probabilities, dtype=float).ravel(), 1e-6, 1 - 1e-6)
        y = np.asarray(targets, dtype=int).ravel()
        if np.unique(y).size < 2:
            return self
        logits = np.log(p / (1 - p)).reshape(-1, 1)
        self.model.fit(logits, y); self.fitted = True
        return self

    def transform(self, probabilities: np.ndarray) -> np.ndarray:
        p = np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1 - 1e-6)
        if not self.fitted:
            return p
        logits = np.log(p / (1 - p)).reshape(-1, 1)
        return self.model.predict_proba(logits)[:, 1].reshape(p.shape)


class TemperatureScaler:
    def __init__(self, temperature: float = 1.0):
        self.temperature = temperature

    def fit(self, logits: np.ndarray, targets: np.ndarray) -> "TemperatureScaler":
        logits = np.asarray(logits, dtype=float); targets = np.asarray(targets, dtype=int)
        best = (float("inf"), 1.0)
        for t in np.geomspace(0.25, 4.0, 80):
            shifted = logits / t
            shifted -= shifted.max(axis=1, keepdims=True)
            probs = np.exp(shifted); probs /= probs.sum(axis=1, keepdims=True)
            loss = -np.log(np.clip(probs[np.arange(len(targets)), targets], 1e-12, 1)).mean()
            if loss < best[0]: best = (float(loss), float(t))
        self.temperature = best[1]
        return self

    def transform(self, logits: np.ndarray) -> np.ndarray:
        shifted = np.asarray(logits, dtype=float) / self.temperature
        shifted -= shifted.max(axis=1, keepdims=True)
        probs = np.exp(shifted)
        return probs / probs.sum(axis=1, keepdims=True)

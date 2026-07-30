from __future__ import annotations

import numpy as np
import pandas as pd


class PositionFrequencyAdapter:
    model_id = "position-frequency"

    def __init__(self, alpha: float = 2.0):
        self.alpha = alpha
        self.probabilities = np.full((7, 37), 1 / 37, dtype=float)

    def fit(self, master: pd.DataFrame) -> "PositionFrequencyAdapter":
        for pos in range(1, 8):
            col = f"n{pos}"
            counts = master[col].value_counts().reindex(range(1, 38), fill_value=0).to_numpy(dtype=float)
            probs = (counts + self.alpha / 37) / (len(master) + self.alpha)
            self.probabilities[pos - 1] = probs / probs.sum()
        return self

    def predict_matrix(self) -> np.ndarray:
        return self.probabilities.copy()

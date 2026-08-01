from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from loto.models.base import ModelAdapter, ModelCapabilities


class UniformCandidateAdapter(ModelAdapter):
    model_id = "uniform-7-over-37"
    capabilities = ModelCapabilities.PROBABILITY_PREDICTION | ModelCapabilities.RANKING_PREDICTION

    def fit(self, data: pd.DataFrame) -> UniformCandidateAdapter:
        return self

    def predict(self, data: pd.DataFrame) -> pd.DataFrame:
        self.validate_request(data)
        out = data[["candidate_number"]].copy()
        out["probability"] = 7 / 37
        out["rank_score"] = 0.0
        return out


class FrequencyCandidateAdapter(ModelAdapter):
    capabilities = ModelCapabilities.PROBABILITY_PREDICTION | ModelCapabilities.RANKING_PREDICTION

    def __init__(self, alpha: float = 5.0):
        self.alpha = float(alpha)
        self.model_id = f"frequency-alpha-{self.alpha:g}"
        self._probabilities = np.full(37, 7 / 37, dtype=float)

    def fit(self, data: pd.DataFrame) -> FrequencyCandidateAdapter:
        self.validate_request(data)
        if not {"candidate_number", "selected"}.issubset(data.columns):
            raise ValueError("frequency model requires candidate_number and selected")
        grouped = data.groupby("candidate_number")["selected"].agg(["sum", "count"])
        prior = 7 / 37
        for candidate in range(1, 38):
            if candidate in grouped.index:
                row = grouped.loc[candidate]
                self._probabilities[candidate - 1] = (float(row["sum"]) + self.alpha * prior) / (
                    float(row["count"]) + self.alpha
                )
        return self

    def predict(self, data: pd.DataFrame) -> pd.DataFrame:
        self.validate_request(data)
        out = data[["candidate_number"]].copy()
        out["probability"] = out["candidate_number"].map(lambda n: self._probabilities[int(n) - 1])
        out["rank_score"] = out["probability"]
        return out

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({"alpha": self.alpha, "probabilities": self._probabilities.tolist()})
        )
        return p

    def load(self, path: str | Path) -> FrequencyCandidateAdapter:
        obj = json.loads(Path(path).read_text())
        self.alpha = float(obj["alpha"])
        self._probabilities = np.asarray(obj["probabilities"], dtype=float)
        return self


class LogisticCandidateAdapter(ModelAdapter):
    capabilities = (
        ModelCapabilities.PROBABILITY_PREDICTION
        | ModelCapabilities.RANKING_PREDICTION
        | ModelCapabilities.EXOGENOUS_FEATURES
    )

    def __init__(self, c: float = 0.2, random_state: int = 42):
        self.model_id = f"logistic-c-{c:g}"
        self.c = c
        self.random_state = random_state
        self.model = LogisticRegression(
            C=c, class_weight="balanced", max_iter=1000, random_state=random_state
        )
        self.feature_columns: list[str] = []
        self._fitted = False

    def fit(self, data: pd.DataFrame) -> LogisticCandidateAdapter:
        self.validate_request(data)
        excluded = {"draw_id", "draw_no", "draw_date", "selected", "candidate_number"}
        self.feature_columns = [
            c for c in data.columns if c not in excluded and pd.api.types.is_numeric_dtype(data[c])
        ]
        if not self.feature_columns or data["selected"].nunique() < 2:
            return self
        self.model.fit(data[self.feature_columns], data["selected"])
        self._fitted = True
        return self

    def predict(self, data: pd.DataFrame) -> pd.DataFrame:
        self.validate_request(data)
        out = data[["candidate_number"]].copy()
        if self._fitted:
            p = self.model.predict_proba(data[self.feature_columns])[:, 1]
        else:
            p = np.full(len(data), 7 / 37)
        out["probability"] = np.clip(p, 1e-6, 1 - 1e-6)
        out["rank_score"] = out["probability"]
        return out

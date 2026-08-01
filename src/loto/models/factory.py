from __future__ import annotations

import importlib
import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.models.baselines import FrequencyCandidateAdapter, UniformCandidateAdapter
from loto.models.catalog import ModelSpec, get_model_spec

FEATURE_EXCLUDE = {
    "draw_no",
    "draw_date",
    "candidate_number",
    "target",
    "next_target",
    "hit",
    "y",
    "unique_id",
    "ds",
    "position",
    "actual",
}


def numeric_feature_columns(frame: pd.DataFrame) -> list[str]:
    return [
        col
        for col in frame.columns
        if col not in FEATURE_EXCLUDE and pd.api.types.is_numeric_dtype(frame[col])
    ]


@dataclass
class PredictionResult:
    candidate_probabilities: np.ndarray | None = None
    position_values: np.ndarray | None = None
    metadata: dict[str, Any] | None = None


class RuntimeModel:
    def __init__(self, spec: ModelSpec, params: dict[str, Any] | None = None, *, seed: int = 42):
        self.spec = spec
        self.params = spec.default_params | (params or {})
        self.seed = seed
        self.model: Any = None
        self.feature_columns: list[str] = []

    def fit_candidate(self, train: pd.DataFrame, target_column: str = "selected") -> RuntimeModel:
        if self.spec.model_id == "uniform":
            self.model = UniformCandidateAdapter().fit(train)
            return self
        if self.spec.model_id == "frequency":
            self.model = FrequencyCandidateAdapter().fit(train)
            return self
        if target_column not in train:
            raise ValueError(f"target column is missing: {target_column}")
        self.feature_columns = [
            column for column in numeric_feature_columns(train) if column != target_column
        ]
        if target_column in self.feature_columns:
            raise RuntimeError(f"target column leaked into features: {target_column}")
        if not self.feature_columns:
            raise ValueError("no numeric model features")
        X = train[self.feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        y = train[target_column].astype(int)
        self.model = self._construct_estimator()
        self.model.fit(X, y)
        return self

    def _prepare_query_features(self, query: pd.DataFrame) -> pd.DataFrame:
        missing_columns = [column for column in self.feature_columns if column not in query.columns]
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"query is missing fitted feature columns: {missing}")

        return query.loc[:, self.feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    def predict_candidate(self, query: pd.DataFrame) -> PredictionResult:
        if self.spec.model_id in {"uniform", "frequency"}:
            out = self.model.predict(query)
            return PredictionResult(
                candidate_probabilities=out["probability"].to_numpy(float),
                metadata={"rank_score": out["rank_score"].to_numpy(float).tolist()},
            )
        X = self._prepare_query_features(query)
        if hasattr(self.model, "predict_proba"):
            probabilities = self.model.predict_proba(X)
            probability = (
                probabilities[:, 1]
                if probabilities.ndim == 2 and probabilities.shape[1] > 1
                else probabilities.ravel()
            )
        elif hasattr(self.model, "decision_function"):
            raw = np.asarray(self.model.decision_function(X), dtype=float)
            probability = 1.0 / (1.0 + np.exp(-raw))
        else:
            probability = np.clip(np.asarray(self.model.predict(X), dtype=float), 0.0, 1.0)
        return PredictionResult(candidate_probabilities=probability, metadata={})

    def fit_position(self, train_x: pd.DataFrame, train_y: np.ndarray) -> RuntimeModel:
        self.feature_columns = numeric_feature_columns(train_x)
        X = train_x[self.feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        self.model = self._construct_estimator(regression=True)
        self.model.fit(X, train_y)
        return self

    def predict_position(self, query: pd.DataFrame) -> PredictionResult:
        X = self._prepare_query_features(query)
        values = np.asarray(self.model.predict(X), dtype=float)
        return PredictionResult(position_values=values, metadata={})

    def _construct_estimator(self, regression: bool = False):
        model_id = self.spec.model_id
        params = dict(self.params)
        if self.spec.library == "sklearn":
            if model_id == "logistic":
                from sklearn.linear_model import LogisticRegression

                return LogisticRegression(random_state=self.seed, **params)
            if model_id == "ridge-position":
                from sklearn.linear_model import Ridge

                return Ridge(**params)
            if model_id == "elasticnet-position":
                from sklearn.linear_model import ElasticNet

                return ElasticNet(random_state=self.seed, **params)
            if model_id == "random-forest":
                from sklearn.ensemble import RandomForestClassifier

                return RandomForestClassifier(random_state=self.seed, **params)
            if model_id == "extra-trees":
                from sklearn.ensemble import ExtraTreesClassifier

                return ExtraTreesClassifier(random_state=self.seed, **params)
            if model_id == "hist-gradient-boosting":
                from sklearn.ensemble import HistGradientBoostingClassifier

                return HistGradientBoostingClassifier(random_state=self.seed, **params)
        if self.spec.library == "lightgbm":
            module = importlib.import_module("lightgbm")
            cls = getattr(module, self.spec.class_name)
            params.setdefault("random_state", self.seed)
            params.setdefault("verbosity", -1)
            return cls(**params)
        if self.spec.library == "xgboost":
            module = importlib.import_module("xgboost")
            cls = getattr(module, self.spec.class_name)
            params.setdefault("random_state", self.seed)
            params.setdefault("n_jobs", 1)
            return cls(**params)
        if self.spec.library == "catboost":
            module = importlib.import_module("catboost")
            cls = getattr(module, self.spec.class_name)
            params.setdefault("random_seed", self.seed)
            return cls(**params)
        raise NotImplementedError(
            f"model {model_id} uses worker adapter "
            f"{self.spec.library}; invoke through WorkerGateway"
        )

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as stream:
            pickle.dump(
                {
                    "spec": self.spec.to_dict(),
                    "params": self.params,
                    "seed": self.seed,
                    "feature_columns": self.feature_columns,
                    "model": self.model,
                },
                stream,
            )
        return path

    @classmethod
    def load(cls, path: str | Path) -> RuntimeModel:
        with Path(path).open("rb") as stream:
            payload = pickle.load(stream)
        runtime = cls(
            get_model_spec(payload["spec"]["model_id"]),
            payload["params"],
            seed=int(payload["seed"]),
        )
        runtime.feature_columns = list(payload["feature_columns"])
        runtime.model = payload["model"]
        return runtime


class WorkerGateway:
    """Uniform process boundary for optional heavy model libraries.

    Built-in/sklearn models run in-process. Nixtla and TSFM workers are represented
    by deterministic job documents so they can run in a subprocess/container without
    contaminating the orchestrator environment.
    """

    def build_job(
        self,
        model_id: str,
        *,
        params: dict[str, Any],
        input_uri: str,
        output_uri: str,
        seed: int,
        device: str,
        precision: str,
    ) -> dict[str, Any]:
        spec = get_model_spec(model_id)
        return {
            "schema_version": "2.1.0",
            "model": spec.to_dict(),
            "params": spec.default_params | params,
            "input_uri": input_uri,
            "output_uri": output_uri,
            "seed": seed,
            "device": device,
            "precision": precision,
        }

    @staticmethod
    def write_job(job: dict[str, Any], path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

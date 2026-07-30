from __future__ import annotations

from abc import ABC, abstractmethod
from enum import IntFlag, auto
from pathlib import Path
from typing import Any

import pandas as pd


class ModelCapabilities(IntFlag):
    PROBABILITY_PREDICTION = auto()
    RANKING_PREDICTION = auto()
    POSITION_PREDICTION = auto()
    EXOGENOUS_FEATURES = auto()
    WARM_START = auto()
    GPU_TRAINING = auto()
    CHECKPOINTING = auto()
    ZERO_SHOT = auto()
    FINE_TUNING = auto()


class ModelAdapter(ABC):
    model_id: str
    capabilities: ModelCapabilities

    def validate_request(self, data: pd.DataFrame) -> None:
        if data.empty:
            raise ValueError("training/prediction data must not be empty")

    @abstractmethod
    def fit(self, data: pd.DataFrame) -> "ModelAdapter": ...

    @abstractmethod
    def predict(self, data: pd.DataFrame) -> pd.DataFrame: ...

    def save(self, path: str | Path) -> Path:
        raise NotImplementedError

    def load(self, path: str | Path) -> "ModelAdapter":
        raise NotImplementedError

    def get_metadata(self) -> dict[str, Any]:
        return {"model_id": self.model_id, "capabilities": int(self.capabilities)}

    def get_resource_requirements(self) -> dict[str, Any]:
        return {"cpu": 1, "gpu": 0, "memory_mb": 256}

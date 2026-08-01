from __future__ import annotations

# ruff: noqa: E501
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.models.catalog import ModelSpec


class FoundationProviderError(RuntimeError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


class FoundationProvider(ABC):
    def __init__(
        self, spec: ModelSpec, params: dict[str, Any], *, seed: int, device: str, precision: str
    ):
        self.spec = spec
        self.params = params
        self.seed = seed
        self.device = device
        self.precision = precision

    @abstractmethod
    def validate_environment(self) -> dict[str, Any]: ...

    @abstractmethod
    def load(self) -> FoundationProvider: ...

    def fit_or_prepare(self, history: pd.DataFrame) -> FoundationProvider:
        return self

    @abstractmethod
    def predict(self, history: pd.DataFrame) -> np.ndarray: ...

    def save(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        (path / "provider.json").write_text(
            '{"status":"UNSUPPORTED_OPERATION","reason":"provider does not expose a local model artifact"}',
            encoding="utf-8",
        )
        return path

    def load_saved(self, path: Path) -> FoundationProvider:
        if not path.exists():
            raise FoundationProviderError("ARTIFACT_MISSING", f"provider artifact missing: {path}")
        return self

    def retrain(self, history: pd.DataFrame) -> FoundationProvider:
        raise FoundationProviderError(
            "UNSUPPORTED_OPERATION", "zero-shot provider does not support retraining"
        )

    def inspect_properties(self) -> dict[str, Any]:
        return {
            "model_id": self.spec.model_id,
            "library": self.spec.library,
            "class_name": self.spec.class_name,
            "fit_supported": False,
            "predict_supported": True,
            "save_supported": True,
            "load_supported": True,
            "device": self.device,
            "precision": self.precision,
        }

    def close(self) -> None:
        return None

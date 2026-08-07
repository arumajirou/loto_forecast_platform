from __future__ import annotations

from collections.abc import Iterable

from .contracts import ModelDescriptor
from .errors import ConfigurationError


class ModelRegistry:
    def __init__(self, models: Iterable[ModelDescriptor] = ()) -> None:
        self._models: dict[str, ModelDescriptor] = {}
        for model in models:
            self.upsert(model)

    def upsert(self, model: ModelDescriptor) -> None:
        self._models[model.key] = model

    def get(self, key: str) -> ModelDescriptor:
        try:
            return self._models[key]
        except KeyError as exc:
            raise ConfigurationError(f"unknown model: {key}") from exc

    def all(self) -> list[ModelDescriptor]:
        return list(self._models.values())

    def enabled(self) -> list[ModelDescriptor]:
        return [model for model in self._models.values() if model.enabled]

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from ..contracts import (
    ChatRequest,
    ChatResponse,
    HealthReport,
    LoadedModel,
    LoadRequest,
    ModelDescriptor,
)


class InferenceEngine(ABC):
    def __init__(self, endpoint: str, api_key: str | None = None) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key

    @property
    def headers(self) -> dict[str, str]:
        result = {"Content-Type": "application/json"}
        if self.api_key:
            result["Authorization"] = f"Bearer {self.api_key}"
        return result

    @abstractmethod
    async def health(self) -> HealthReport:
        raise NotImplementedError

    @abstractmethod
    async def discover(self) -> list[ModelDescriptor]:
        raise NotImplementedError

    async def load(self, request: LoadRequest) -> LoadedModel:
        raise NotImplementedError("engine does not support explicit loading")

    async def unload(self, instance_id: str) -> None:
        raise NotImplementedError("engine does not support explicit unloading")

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[bytes]:
        raise NotImplementedError("engine does not support streaming")
        yield b""  # pragma: no cover

    async def raw_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("engine does not support raw forwarding")

    async def stream_raw(self, path: str, payload: dict[str, Any]) -> AsyncIterator[bytes]:
        raise NotImplementedError("engine does not support raw streaming")
        yield b""  # pragma: no cover

    async def close(self) -> None:
        return None

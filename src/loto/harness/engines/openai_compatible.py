from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ..contracts import (
    Capability,
    ChatRequest,
    ChatResponse,
    EngineKind,
    EngineTimings,
    HarnessStatus,
    HealthReport,
    ModelDescriptor,
    Usage,
)
from ..errors import EngineUnavailable
from .base import InferenceEngine
from .http_client import HttpJsonClient


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class OpenAICompatibleEngine(InferenceEngine):
    kind = EngineKind.OPENAI_COMPATIBLE

    def __init__(
        self,
        endpoint: str,
        api_key: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 180,
    ) -> None:
        super().__init__(endpoint, api_key)
        self.http = HttpJsonClient(
            timeout_seconds=timeout_seconds,
            retries=1,
            transport=transport,
        )

    async def health(self) -> HealthReport:
        try:
            await self.http.request(
                "GET",
                f"{self.endpoint}/v1/models",
                headers=self.headers,
            )
            return HealthReport(
                engine=self.kind,
                endpoint=self.endpoint,
                status=HarnessStatus.VERIFIED,
            )
        except EngineUnavailable as exc:
            return HealthReport(
                engine=self.kind,
                endpoint=self.endpoint,
                status=HarnessStatus.BLOCKED,
                detail=str(exc),
            )

    async def discover(self) -> list[ModelDescriptor]:
        payload = await self.http.request(
            "GET",
            f"{self.endpoint}/v1/models",
            headers=self.headers,
        )
        models: list[ModelDescriptor] = []
        raw_models = payload.get("data")
        for item in raw_models if isinstance(raw_models, list) else []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            meta = _as_dict(item.get("meta"))
            models.append(
                ModelDescriptor(
                    key=str(item["id"]),
                    display_name=str(item.get("id")),
                    engine=self.kind,
                    endpoint=self.endpoint,
                    declared_context=int(meta.get("n_ctx_train") or 8192),
                    capabilities={Capability.CHAT},
                    status=HarnessStatus.DISCOVERED,
                )
            )
        return models

    @staticmethod
    def _payload(request: ChatRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [message.model_dump(exclude_none=True) for message in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": request.stream,
        }
        if request.tools is not None:
            payload["tools"] = request.tools
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice
        optional = {
            "top_p": request.top_p,
            "top_k": request.top_k,
            "min_p": request.min_p,
            "presence_penalty": request.presence_penalty,
            "frequency_penalty": request.frequency_penalty,
            "seed": request.seed,
            "stop": request.stop,
        }
        payload.update({key: value for key, value in optional.items() if value is not None})
        if request.response_format is not None:
            payload["response_format"] = request.response_format
        payload.update(request.extra_body)
        return payload

    async def chat(self, request: ChatRequest) -> ChatResponse:
        if request.stream:
            raise EngineUnavailable("use stream_chat for streaming requests")
        started = time.monotonic()
        payload = await self.raw_post("/v1/chat/completions", self._payload(request))
        total_seconds = time.monotonic() - started

        raw_choices = payload.get("choices")
        choices = raw_choices if isinstance(raw_choices, list) else []
        choice = _as_dict(choices[0]) if choices else {}
        message = _as_dict(choice.get("message"))
        usage_raw = _as_dict(payload.get("usage"))
        details = _as_dict(usage_raw.get("prompt_tokens_details"))
        timings_raw = _as_dict(payload.get("timings"))
        raw_tool_calls = message.get("tool_calls")
        tool_calls = raw_tool_calls if isinstance(raw_tool_calls, list) else []

        return ChatResponse(
            model=str(payload.get("model") or request.model or "unknown"),
            content=str(message.get("content") or ""),
            reasoning_content=(
                str(message["reasoning_content"])
                if message.get("reasoning_content") is not None
                else None
            ),
            finish_reason=(
                str(choice["finish_reason"]) if choice.get("finish_reason") is not None else None
            ),
            tool_calls=[item for item in tool_calls if isinstance(item, dict)],
            usage=Usage(
                prompt_tokens=int(usage_raw.get("prompt_tokens") or 0),
                completion_tokens=int(usage_raw.get("completion_tokens") or 0),
                total_tokens=int(usage_raw.get("total_tokens") or 0),
                cached_tokens=int(details.get("cached_tokens") or timings_raw.get("cache_n") or 0),
            ),
            timings=EngineTimings(
                total_seconds=total_seconds,
                prompt_tokens_per_second=timings_raw.get("prompt_per_second"),
                generation_tokens_per_second=timings_raw.get("predicted_per_second"),
            ),
            raw=payload,
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[bytes]:
        payload = self._payload(request)
        payload["stream"] = True
        async for chunk in self.stream_raw("/v1/chat/completions", payload):
            yield chunk

    async def raw_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.http.request(
            "POST",
            f"{self.endpoint}{path}",
            headers=self.headers,
            json=payload,
        )

    async def stream_raw(
        self,
        path: str,
        payload: dict[str, Any],
    ) -> AsyncIterator[bytes]:
        async for chunk in self.http.stream_bytes(
            "POST",
            f"{self.endpoint}{path}",
            headers=self.headers,
            json=payload,
        ):
            yield chunk

    async def close(self) -> None:
        await self.http.close()

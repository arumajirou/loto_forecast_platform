from __future__ import annotations

import time
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


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _uses_modern_gemini_3_config(model: str | None) -> bool:
    """Return whether deprecated sampling parameters must be omitted.

    Gemini 3.6 Flash and Gemini 3.5 Flash-Lite introduced the current Gemini
    3 request contract. These models reject or ignore temperature, top_p, and
    top_k, and use thinking_level instead.
    """

    key = (model or "").lower()
    return key.startswith("gemini-3.6-") or key.startswith("gemini-3.5-flash-lite")


class GeminiEngine(InferenceEngine):
    kind = EngineKind.GEMINI

    def __init__(
        self,
        endpoint: str = "https://generativelanguage.googleapis.com",
        api_key: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 300,
    ) -> None:
        super().__init__(endpoint, api_key)
        self.http = HttpJsonClient(
            timeout_seconds=timeout_seconds,
            retries=1,
            transport=transport,
        )

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-goog-api-key"] = self.api_key
        return headers

    async def health(self) -> HealthReport:
        if not self.api_key:
            return HealthReport(
                engine=self.kind,
                endpoint=self.endpoint,
                status=HarnessStatus.BLOCKED,
                detail="GEMINI_API_KEY is not configured",
            )
        try:
            await self.http.request(
                "GET",
                f"{self.endpoint}/v1beta/models?pageSize=1",
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
            f"{self.endpoint}/v1beta/models?pageSize=1000",
            headers=self.headers,
        )
        result: list[ModelDescriptor] = []
        for item in _list(payload.get("models")):
            if not isinstance(item, dict):
                continue
            raw_name = item.get("baseModelId") or item.get("name")
            if not raw_name:
                continue
            key = str(raw_name).removeprefix("models/")
            methods = {str(value) for value in _list(item.get("supportedGenerationMethods"))}
            capabilities = {Capability.CHAT}
            if any("embed" in value.lower() for value in methods):
                capabilities = {Capability.EMBEDDING}
            else:
                capabilities.update(
                    {
                        Capability.TOOLS,
                        Capability.JSON_SCHEMA,
                        Capability.REASONING,
                        Capability.VISION,
                    }
                )
            result.append(
                ModelDescriptor(
                    key=key,
                    display_name=str(item.get("displayName") or key),
                    engine=self.kind,
                    endpoint=self.endpoint,
                    provider="google",
                    profile_id="gemini-interactions",
                    declared_context=int(item.get("inputTokenLimit") or 8192),
                    capabilities=capabilities,
                    status=HarnessStatus.DISCOVERED,
                )
            )
        return result

    @staticmethod
    def _interaction_input(request: ChatRequest) -> str | list[dict[str, Any]]:
        if request.provider_history:
            return request.provider_history
        non_system = [message for message in request.messages if message.role != "system"]
        if len(non_system) == 1 and non_system[0].role == "user":
            return non_system[0].content
        inputs: list[dict[str, Any]] = []
        for message in non_system:
            if message.role == "user":
                inputs.append({"type": "user_input", "content": message.content})
            elif message.role == "assistant":
                inputs.append(
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": message.content}],
                    }
                )
            elif message.role == "tool":
                inputs.append(
                    {
                        "type": "function_result",
                        "name": message.name or "tool",
                        "call_id": message.tool_call_id or "unknown",
                        "result": [{"type": "text", "text": message.content}],
                    }
                )
        return inputs

    @staticmethod
    def _tools(request: ChatRequest) -> list[dict[str, Any]] | None:
        if not request.tools:
            return None
        converted: list[dict[str, Any]] = []
        for tool in request.tools:
            if not isinstance(tool, dict):
                continue
            function = _dict(tool.get("function"))
            if function:
                converted.append(
                    {
                        "type": "function",
                        "name": function.get("name"),
                        "description": function.get("description", ""),
                        "parameters": function.get("parameters", {"type": "object"}),
                    }
                )
            else:
                converted.append(tool)
        return converted or None

    @classmethod
    def _tool_choice(cls, request: ChatRequest) -> dict[str, Any] | None:
        if request.tool_choice is None:
            return None
        if isinstance(request.tool_choice, dict):
            return request.tool_choice
        names = [
            str(_dict(tool.get("function")).get("name"))
            for tool in request.tools or []
            if _dict(tool.get("function")).get("name")
        ]
        mode_map = {
            "required": "any",
            "auto": "auto",
            "none": "none",
            "validated": "validated",
        }
        mode = mode_map.get(str(request.tool_choice), str(request.tool_choice))
        return {"allowed_tools": {"mode": mode, "tools": names}}

    @staticmethod
    def _response_format(request: ChatRequest) -> dict[str, Any] | None:
        value = request.response_format
        if not isinstance(value, dict):
            return None
        if value.get("type") == "json_schema":
            raw = _dict(value.get("json_schema"))
            schema = _dict(raw.get("schema"))
            return {
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            }
        return value

    @classmethod
    def _payload(cls, request: ChatRequest) -> dict[str, Any]:
        modern_gemini_3 = _uses_modern_gemini_3_config(request.model)
        generation_config: dict[str, Any] = {
            "max_output_tokens": request.max_tokens,
        }
        if not modern_gemini_3:
            generation_config["temperature"] = request.temperature
            optional = {
                "top_p": request.top_p,
                "top_k": request.top_k,
                "presence_penalty": request.presence_penalty,
                "frequency_penalty": request.frequency_penalty,
                "seed": request.seed,
            }
            generation_config.update(
                {key: value for key, value in optional.items() if value is not None}
            )
        if request.extra_body.get("thinking_level") is not None:
            generation_config["thinking_level"] = request.extra_body["thinking_level"]

        payload: dict[str, Any] = {
            "model": request.model,
            "input": cls._interaction_input(request),
            "generation_config": generation_config,
            "store": False,
        }
        system = request.system_instruction or "\n\n".join(
            message.content for message in request.messages if message.role == "system"
        )
        if system:
            payload["system_instruction"] = system
        tools = cls._tools(request)
        if tools:
            payload["tools"] = tools
        tool_choice = cls._tool_choice(request)
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        response_format = cls._response_format(request)
        if response_format is not None:
            payload["response_format"] = response_format
        for key, value in request.extra_body.items():
            if key not in {"thinking_level"}:
                payload[key] = value
        return payload

    async def chat(self, request: ChatRequest) -> ChatResponse:
        if not self.api_key:
            raise EngineUnavailable("GEMINI_API_KEY is not configured")
        started = time.monotonic()
        payload = await self.http.request(
            "POST",
            f"{self.endpoint}/v1beta/interactions",
            headers=self.headers,
            json=self._payload(request),
        )
        total_seconds = time.monotonic() - started
        output_text = str(payload.get("output_text") or "")
        reasoning_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        if not output_text:
            text_parts: list[str] = []
            for step in _list(payload.get("steps")) + _list(payload.get("output")):
                if not isinstance(step, dict):
                    continue
                step_type = str(step.get("type") or "")
                if step_type in {"thought", "reasoning"}:
                    thought = step.get("text") or step.get("content")
                    if isinstance(thought, str):
                        reasoning_parts.append(thought)
                if step_type == "function_call":
                    tool_calls.append(
                        {
                            "id": step.get("id") or step.get("call_id"),
                            "type": "function",
                            "function": {
                                "name": step.get("name"),
                                "arguments": step.get("arguments") or {},
                            },
                        }
                    )
                content = step.get("text") or step.get("content")
                if isinstance(content, str):
                    text_parts.append(content)
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            text_parts.append(part["text"])
            output_text = "".join(text_parts)
        usage_raw = _dict(payload.get("usage") or payload.get("usage_metadata"))
        return ChatResponse(
            model=str(payload.get("model") or request.model or "unknown"),
            content=output_text,
            reasoning_content="\n".join(reasoning_parts) or None,
            finish_reason=str(payload.get("status") or payload.get("stop_reason") or "stop"),
            tool_calls=tool_calls,
            usage=Usage(
                prompt_tokens=int(
                    usage_raw.get("input_tokens")
                    or usage_raw.get("prompt_token_count")
                    or 0
                ),
                completion_tokens=int(
                    usage_raw.get("output_tokens")
                    or usage_raw.get("candidates_token_count")
                    or 0
                ),
                total_tokens=int(
                    usage_raw.get("total_tokens")
                    or usage_raw.get("total_token_count")
                    or 0
                ),
                cached_tokens=int(
                    usage_raw.get("total_cached_tokens")
                    or usage_raw.get("cached_content_token_count")
                    or 0
                ),
            ),
            timings=EngineTimings(total_seconds=total_seconds),
            raw=payload,
        )

    async def close(self) -> None:
        await self.http.close()

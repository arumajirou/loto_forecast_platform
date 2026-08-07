from __future__ import annotations

import asyncio

import httpx

from loto.harness.contracts import ChatRequest, Message
from loto.harness.engines.gemini import GeminiEngine


def test_gemini_discovery_and_interactions_payload() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "models/gemini-3.6-flash",
                            "baseModelId": "gemini-3.6-flash",
                            "displayName": "Gemini 3.6 Flash",
                            "inputTokenLimit": 1048576,
                            "supportedGenerationMethods": ["generateContent"],
                        }
                    ]
                },
            )
        seen["header"] = request.headers.get("x-goog-api-key")
        seen["payload"] = __import__("json").loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "gemini-3.6-flash",
                "output_text": "PROFILE_AB_OK",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 3,
                    "total_tokens": 13,
                    "total_cached_tokens": 4,
                },
            },
        )

    async def run() -> None:
        engine = GeminiEngine(
            api_key="secret",
            transport=httpx.MockTransport(handler),
        )
        models = await engine.discover()
        assert models[0].profile_id == "gemini-interactions"
        assert models[0].declared_context == 1048576
        response = await engine.chat(
            ChatRequest(
                model="gemini-3.6-flash",
                messages=[
                    Message(role="system", content="Be precise"),
                    Message(role="user", content="hello"),
                ],
                system_instruction="Be precise",
                top_p=0.9,
                max_tokens=64,
            )
        )
        assert response.content == "PROFILE_AB_OK"
        assert response.usage.cached_tokens == 4
        assert seen["header"] == "secret"
        payload = seen["payload"]
        assert isinstance(payload, dict)
        assert payload["system_instruction"] == "Be precise"
        generation_config = payload["generation_config"]
        assert generation_config["max_output_tokens"] == 64
        assert "temperature" not in generation_config
        assert "top_p" not in generation_config
        assert "top_k" not in generation_config
        await engine.close()

    asyncio.run(run())


def test_gemini_maps_openai_schema_tools_and_provider_history() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["payload"] = __import__("json").loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "gemini-3.6-flash",
                "steps": [
                    {"type": "thought", "text": "internal plan"},
                    {
                        "type": "function_call",
                        "id": "call-1",
                        "name": "echo",
                        "arguments": {"value": 7},
                    },
                ],
            },
        )

    async def run() -> None:
        engine = GeminiEngine(
            api_key="secret",
            transport=httpx.MockTransport(handler),
        )
        response = await engine.chat(
            ChatRequest(
                model="gemini-3.6-flash",
                messages=[Message(role="user", content="call echo")],
                provider_history=[
                    {"type": "user_input", "content": "call echo"},
                    {"type": "thought", "text": "preserved"},
                ],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "echo",
                            "description": "Echo an integer",
                            "parameters": {
                                "type": "object",
                                "properties": {"value": {"type": "integer"}},
                                "required": ["value"],
                            },
                        },
                    }
                ],
                tool_choice="required",
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "echo_result",
                        "schema": {
                            "type": "object",
                            "properties": {"value": {"type": "integer"}},
                            "required": ["value"],
                        },
                    },
                },
            )
        )
        payload = seen["payload"]
        assert isinstance(payload, dict)
        assert str(seen["url"]).endswith("/v1beta/interactions")
        assert payload["input"][1]["type"] == "thought"
        assert payload["tool_choice"]["allowed_tools"]["mode"] == "any"
        assert payload["tool_choice"]["allowed_tools"]["tools"] == ["echo"]
        assert payload["response_format"]["mime_type"] == "application/json"
        assert response.reasoning_content == "internal plan"
        assert response.tool_calls[0]["function"]["name"] == "echo"
        await engine.close()

    asyncio.run(run())


def test_gemini_legacy_model_retains_sampling_parameters() -> None:
    request = ChatRequest(
        model="gemini-2.5-flash",
        messages=[Message(role="user", content="hello")],
        temperature=0.4,
        top_p=0.9,
        top_k=20,
        max_tokens=32,
    )
    payload = GeminiEngine._payload(request)
    generation_config = payload["generation_config"]
    assert generation_config["temperature"] == 0.4
    assert generation_config["top_p"] == 0.9
    assert generation_config["top_k"] == 20

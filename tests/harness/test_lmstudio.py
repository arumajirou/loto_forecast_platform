import asyncio

import httpx

from loto.harness.contracts import ChatRequest, LoadRequest, Message
from loto.harness.engines.lmstudio import LMStudioEngine


def test_lmstudio_v1_and_openai_contracts() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/models" and request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "models": [
                            {
                                "type": "llm",
                                "key": "qwen-test",
                                "display_name": "Qwen Test",
                                "architecture": "qwen",
                                "quantization": {"name": "Q4_K_M"},
                                "max_context_length": 65536,
                                "capabilities": {
                                    "vision": False,
                                    "trained_for_tool_use": True,
                                    "reasoning": {"allowed_options": ["on"], "default": "on"},
                                },
                                "loaded_instances": [],
                            }
                        ]
                    },
                )
            if request.url.path == "/api/v1/models/load":
                return httpx.Response(
                    200,
                    json={
                        "type": "llm",
                        "instance_id": "qwen-test-instance",
                        "load_time_seconds": 1.5,
                        "status": "loaded",
                        "load_config": {"context_length": 65536, "flash_attention": True},
                    },
                )
            if request.url.path == "/v1/chat/completions":
                return httpx.Response(
                    200,
                    json={
                        "model": "qwen-test",
                        "choices": [
                            {
                                "message": {"role": "assistant", "content": "ok"},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 10,
                            "completion_tokens": 2,
                            "total_tokens": 12,
                            "prompt_tokens_details": {"cached_tokens": 5},
                        },
                    },
                )
            if request.url.path == "/api/v1/models/unload":
                return httpx.Response(200, json={"instance_id": "qwen-test-instance"})
            return httpx.Response(404, json={"error": request.url.path})

        engine = LMStudioEngine(transport=httpx.MockTransport(handler))
        try:
            assert (await engine.health()).status == "VERIFIED"
            models = await engine.discover()
            assert models[0].key == "qwen-test"
            assert "tools" in models[0].capabilities
            assert "reasoning" in models[0].capabilities
            assert models[0].status == "DISCOVERED"
            loaded = await engine.load(LoadRequest(model="qwen-test", context_length=65536))
            assert loaded.context_length == 65536
            response = await engine.chat(
                ChatRequest(model="qwen-test", messages=[Message(role="user", content="hello")])
            )
            assert response.content == "ok"
            assert response.usage.cached_tokens == 5
            await engine.unload(loaded.instance_id)
        finally:
            await engine.close()

    asyncio.run(scenario())

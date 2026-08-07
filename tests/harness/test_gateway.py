from collections.abc import AsyncIterator

from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry

from loto.harness.config import HarnessSettings
from loto.harness.contracts import (
    Capability,
    ChatResponse,
    EngineKind,
    HarnessStatus,
    HealthReport,
    ModelDescriptor,
)
from loto.harness.engines.base import InferenceEngine
from loto.harness.gateway.app import create_app


class FakeEngine(InferenceEngine):
    async def health(self):
        return HealthReport(
            engine=EngineKind.OPENAI_COMPATIBLE,
            endpoint=self.endpoint,
            status=HarnessStatus.VERIFIED,
        )

    async def discover(self):
        return []

    async def chat(self, request):
        system = request.messages[0].content if request.messages[0].role == "system" else ""
        content = "context-injected" if "commit=abc" in system else "hello"
        return ChatResponse(model=request.model or "fake", content=content)

    async def stream_chat(self, request) -> AsyncIterator[bytes]:
        yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        yield b"data: [DONE]\n\n"

    async def raw_post(self, path, payload):
        return {"path": path, "model": payload["model"], "object": "mock"}

    async def stream_raw(self, path, payload) -> AsyncIterator[bytes]:
        yield f"data: {path}:{payload['model']}\n\n".encode()


def build_client() -> TestClient:
    chat_model = ModelDescriptor(
        key="fake-model",
        engine=EngineKind.OPENAI_COMPATIBLE,
        endpoint="http://fake",
        capabilities={Capability.CHAT},
        declared_context=65536,
        status=HarnessStatus.VERIFIED,
    )
    embedding_model = ModelDescriptor(
        key="embed-model",
        engine=EngineKind.OPENAI_COMPATIBLE,
        endpoint="http://fake",
        capabilities={Capability.EMBEDDING},
        declared_context=2048,
        status=HarnessStatus.VERIFIED,
    )
    settings = HarnessSettings(models=[chat_model, embedding_model])
    engine = FakeEngine("http://fake")
    app = create_app(
        settings,
        {"openai_compatible:http://fake": engine},
        prometheus_registry=CollectorRegistry(),
    )
    return TestClient(app)


def test_gateway_models_context_and_chat() -> None:
    with build_client() as client:
        assert client.get("/health").status_code == 200
        models = client.get("/v1/models").json()
        assert {item["id"] for item in models["data"]} == {"fake-model", "embed-model"}
        chat = client.post(
            "/v1/chat/completions",
            json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert chat.status_code == 200
        assert chat.json()["choices"][0]["message"]["content"] == "hello"
        injected = client.post(
            "/v1/chat/completions",
            json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "hi"}],
                "metadata": {
                    "harness_context_items": [
                        {
                            "item_id": "source",
                            "kind": "git",
                            "content": "commit=abc",
                            "priority": "protected",
                        }
                    ]
                },
            },
        )
        assert injected.json()["choices"][0]["message"]["content"] == "context-injected"
        compiled = client.post(
            "/api/v1/context/compile",
            json={
                "total_tokens": 1024,
                "output_reserve_tokens": 128,
                "items": [
                    {
                        "item_id": "x",
                        "kind": "requirement",
                        "content": "commit=abc",
                        "priority": "protected",
                    }
                ],
            },
        )
        assert compiled.status_code == 200
        assert compiled.json()["protected_loss"] == 0
        assert client.get("/metrics").status_code == 200


def test_gateway_streaming_and_raw_compatibility_routes() -> None:
    with build_client() as client:
        streamed = client.post(
            "/v1/chat/completions",
            json={
                "model": "fake-model",
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert streamed.status_code == 200
        assert "data: [DONE]" in streamed.text

        embeddings = client.post(
            "/v1/embeddings",
            json={"model": "embed-model", "input": "hello"},
        )
        assert embeddings.json()["path"] == "/v1/embeddings"

        responses = client.post(
            "/v1/responses",
            json={"model": "fake-model", "input": "hello"},
        )
        assert responses.json()["path"] == "/v1/responses"

        messages = client.post(
            "/v1/messages",
            json={"model": "fake-model", "messages": []},
        )
        assert messages.json()["path"] == "/v1/messages"


def test_gateway_rejects_oversized_context_and_invalid_reserve() -> None:
    with build_client() as client:
        oversized = client.post(
            "/v1/chat/completions",
            json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "hi"}],
                "metadata": {
                    "harness_context_items": [
                        {
                            "item_id": "large",
                            "kind": "log",
                            "content": "x" * 500_001,
                        }
                    ]
                },
            },
        )
        assert oversized.status_code == 413
        reserve = client.post(
            "/api/v1/context/compile",
            json={"total_tokens": 1024, "output_reserve_tokens": 1024, "items": []},
        )
        assert reserve.status_code == 400


def test_gateway_applies_qwen_profile_to_live_request() -> None:
    seen = {}

    class RecordingEngine(FakeEngine):
        async def chat(self, request):
            seen["request"] = request
            return ChatResponse(model=request.model or "qwen", content="ok")

    model = ModelDescriptor(
        key="qwen3-coder-test",
        engine=EngineKind.LMSTUDIO,
        endpoint="http://qwen",
        architecture="qwen3moe",
        capabilities={Capability.CHAT},
        status=HarnessStatus.VERIFIED,
    )
    settings = HarnessSettings(models=[model])
    app = create_app(
        settings,
        {"lmstudio:http://qwen": RecordingEngine("http://qwen")},
        prometheus_registry=CollectorRegistry(),
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": model.key,
                "profile_mode": "quality",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        assert response.status_code == 200
    request = seen["request"]
    assert "/think" not in request.messages[-1].content
    assert "/no_think" not in request.messages[-1].content
    assert request.temperature == 0.7
    assert request.extra_body["repetition_penalty"] == 1.05
    assert request.metadata["thinking_mode_supported"] is False
    assert request.metadata["profile_id"] == "qwen3"

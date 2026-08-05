from __future__ import annotations

import asyncio
import json

from loto.harness.contracts import (
    Capability,
    ChatRequest,
    ChatResponse,
    EngineKind,
    HarnessStatus,
    HealthReport,
    LoadedModel,
    LoadRequest,
    ModelDescriptor,
)
from loto.harness.engines.base import InferenceEngine
from loto.harness.evaluation import ProfileABEvaluator


class ProfileSensitiveEngine(InferenceEngine):
    def __init__(self) -> None:
        super().__init__("http://test")

    async def health(self) -> HealthReport:
        return HealthReport(
            engine=EngineKind.LMSTUDIO,
            endpoint=self.endpoint,
            status=HarnessStatus.VERIFIED,
        )

    async def discover(self) -> list[ModelDescriptor]:
        return []

    async def load(self, request: LoadRequest) -> LoadedModel:
        return LoadedModel(
            model=request.model,
            instance_id="instance",
            context_length=request.context_length,
            status=HarnessStatus.VERIFIED,
        )

    async def unload(self, instance_id: str) -> None:
        return None

    async def chat(self, request: ChatRequest) -> ChatResponse:
        candidate = request.profile_mode != "generic"
        if request.tools:
            calls = [
                {
                    "type": "function",
                    "function": {"name": "profile_echo", "arguments": {"value": 7}},
                }
            ] if candidate else []
            return ChatResponse(model=request.model or "m", tool_calls=calls)
        if request.response_format:
            content = json.dumps({"status": "VERIFIED", "value": 7}) if candidate else "bad"
            return ChatResponse(model=request.model or "m", content=content)
        text = request.messages[-1].content
        if "(17 + 29) * 3 - 8" in text:
            return ChatResponse(
                model=request.model or "m",
                content="130" if candidate else "129",
            )
        if "def add" in text:
            content = (
                "def add(a: int, b: int) -> int:\n    return a + b"
                if candidate
                else "def add(a: int, b: int) -> int:\n    return a - b"
            )
            return ChatResponse(model=request.model or "m", content=content)
        if "PROFILE_NEEDLE_" in text:
            marker = text.rsplit("<target>", 1)[1].split("</target>", 1)[0]
            return ChatResponse(
                model=request.model or "m",
                content=marker if candidate else "missing",
            )
        return ChatResponse(
            model=request.model or "m",
            content="PROFILE_AB_OK" if candidate else "wrong",
        )


def test_profile_ab_detects_candidate_improvement() -> None:
    async def run() -> None:
        descriptor = ModelDescriptor(
            key="qwen3-test",
            engine=EngineKind.LMSTUDIO,
            endpoint="http://test",
            architecture="qwen3",
            capabilities={Capability.CHAT, Capability.TOOLS, Capability.JSON_SCHEMA},
        )
        result = await ProfileABEvaluator(ProfileSensitiveEngine(), descriptor).run(
            modes=["generic", "quality"],
            repetitions=2,
            context_tokens=2048,
            context_utilization=0.5,
        )
        assert result["best_mode"] == "quality"
        assert result["acceptance"]["candidate_beats_generic"] is True
        assert result["results"]["quality"]["achievement_rate"] == 1.0
        assert result["results"]["quality"]["semantic_achievement_rate"] == 1.0
        assert result["results"]["quality"]["contract_achievement_rate"] == 1.0
        assert result["results"]["generic"]["achievement_rate"] == 0.0
        assert result["best_semantic_mode_by_task"]["long_context"] == "quality"

    asyncio.run(run())


class AllSuccessEngine(InferenceEngine):
    def __init__(self, *, reasoning_content: str = "130") -> None:
        super().__init__("http://test")
        self.reasoning_answer = reasoning_content

    async def health(self) -> HealthReport:
        return HealthReport(
            engine=EngineKind.LMSTUDIO,
            endpoint=self.endpoint,
            status=HarnessStatus.VERIFIED,
        )

    async def discover(self) -> list[ModelDescriptor]:
        return []

    async def load(self, request: LoadRequest) -> LoadedModel:
        return LoadedModel(
            model=request.model,
            instance_id="instance",
            context_length=request.context_length,
            status=HarnessStatus.VERIFIED,
        )

    async def unload(self, instance_id: str) -> None:
        return None

    async def chat(self, request: ChatRequest) -> ChatResponse:
        if request.tools:
            return ChatResponse(
                model=request.model or "m",
                tool_calls=[
                    {
                        "type": "function",
                        "function": {
                            "name": "profile_echo",
                            "arguments": {"value": 7},
                        },
                    }
                ],
            )
        if request.response_format:
            return ChatResponse(
                model=request.model or "m",
                content=json.dumps({"status": "VERIFIED", "value": 7}),
            )
        text = request.messages[-1].content
        if "(17 + 29) * 3 - 8" in text:
            return ChatResponse(model=request.model or "m", content=self.reasoning_answer)
        if "def add" in text:
            return ChatResponse(
                model=request.model or "m",
                content="def add(a: int, b: int) -> int:\n    return a + b",
            )
        if "PROFILE_NEEDLE_" in text:
            marker = text.rsplit("<target>", 1)[1].split("</target>", 1)[0]
            return ChatResponse(model=request.model or "m", content=marker)
        return ChatResponse(model=request.model or "m", content="PROFILE_AB_OK")


def _descriptor() -> ModelDescriptor:
    return ModelDescriptor(
        key="qwen3-test",
        engine=EngineKind.LMSTUDIO,
        endpoint="http://test",
        architecture="qwen3",
        capabilities={Capability.CHAT, Capability.TOOLS, Capability.JSON_SCHEMA},
    )


def test_profile_ab_tie_prefers_generic() -> None:
    async def run() -> None:
        result = await ProfileABEvaluator(AllSuccessEngine(), _descriptor()).run(
            modes=["generic", "tools"],
            repetitions=2,
            context_tokens=2048,
            context_utilization=0.5,
            seed=1,
        )
        assert result["best_mode"] == "generic"
        assert result["acceptance"]["candidate_beats_generic"] is False
        assert result["acceptance"]["best_mode_meets_gate"] is True
        assert all(
            mode == "generic"
            for mode in result["recommended_mode_by_task"].values()
        )

    asyncio.run(run())


def test_profile_ab_records_reasoning_correctness_and_format() -> None:
    async def run() -> None:
        result = await ProfileABEvaluator(
            AllSuccessEngine(reasoning_content="The answer is 130"),
            _descriptor(),
        ).run(
            modes=["generic"],
            repetitions=2,
            context_tokens=2048,
            context_utilization=0.5,
            seed=1,
        )
        reasoning = result["results"]["generic"]["tasks"]["reasoning"]
        assert reasoning["success_rate"] == 0.0
        assert reasoning["criteria_success_rates"]["correctness"] == 1.0
        assert reasoning["criteria_success_rates"]["format_compliance"] == 0.0
        assert reasoning["trials"][0]["response_excerpt"] == "The answer is 130"
        assert reasoning["trials"][0]["response_sha256"]
        assert result["acceptance"]["eligible_modes"] == []
        assert result["best_mode"] is None
        assert result["acceptance"]["best_mode_meets_gate"] is False
        assert result["recommended_mode_by_task"]["reasoning"] is None
        assert (
            result["results"]["generic"]["task_failure_classification"]["reasoning"]
            == "OUTPUT_CONTRACT"
        )
        assert result["best_semantic_mode_by_task"]["reasoning"] == "generic"

    asyncio.run(run())


def test_profile_ab_execution_order_is_seeded() -> None:
    async def evaluate() -> dict[str, object]:
        return await ProfileABEvaluator(AllSuccessEngine(), _descriptor()).run(
            modes=["generic", "fast", "quality"],
            repetitions=2,
            context_tokens=2048,
            context_utilization=0.5,
            seed=7,
        )

    first = asyncio.run(evaluate())
    second = asyncio.run(evaluate())
    assert first["execution_order"] == second["execution_order"]

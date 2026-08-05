import asyncio

from loto.harness.certification.suite import CertificationSuite
from loto.harness.contracts import (
    Capability,
    ChatResponse,
    EngineKind,
    HarnessStatus,
    HealthReport,
    LoadedModel,
    ModelDescriptor,
)
from loto.harness.engines.base import InferenceEngine


class CertEngine(InferenceEngine):
    async def health(self):
        return HealthReport(
            engine=EngineKind.LMSTUDIO,
            endpoint=self.endpoint,
            status=HarnessStatus.VERIFIED,
        )

    async def discover(self):
        return [
            ModelDescriptor(
                key="m",
                engine=EngineKind.LMSTUDIO,
                endpoint=self.endpoint,
                capabilities={
                    Capability.CHAT,
                    Capability.JSON_SCHEMA,
                    Capability.TOOLS,
                },
                declared_context=65536,
            )
        ]

    async def load(self, request):
        return LoadedModel(
            model=request.model,
            instance_id="i",
            context_length=request.context_length,
            status=HarnessStatus.VERIFIED,
        )

    async def chat(self, request):
        if request.tools:
            assert request.tool_choice == "required"
            return ChatResponse(
                model="m",
                tool_calls=[{"function": {"name": "certification_echo"}}],
            )
        if "HARNESS_SMOKE_OK" in request.messages[0].content:
            return ChatResponse(model="m", content="HARNESS_SMOKE_OK")
        return ChatResponse(model="m", content='{"status":"VERIFIED","value":7}')

    async def unload(self, instance_id):
        return None


def test_certification_happy_path() -> None:
    async def scenario():
        engine = CertEngine("http://test")
        steps = await CertificationSuite(engine).run("m", contexts=[8192, 65536])
        assert all(step.status == HarnessStatus.VERIFIED for step in steps)
        assert steps[-1].name == "final_unload"

    asyncio.run(scenario())

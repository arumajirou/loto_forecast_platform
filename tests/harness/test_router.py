from loto.harness.contracts import (
    Capability,
    EngineKind,
    HarnessStatus,
    ModelDescriptor,
    ModelPerformance,
)
from loto.harness.registry import ModelRegistry
from loto.harness.router import ModelRouter, RouteRequest


def make_model(key: str, quality: float, tools: bool) -> ModelDescriptor:
    capabilities = {Capability.CHAT}
    if tools:
        capabilities.add(Capability.TOOLS)
    return ModelDescriptor(
        key=key,
        engine=EngineKind.LMSTUDIO,
        endpoint="http://127.0.0.1:1234",
        capabilities=capabilities,
        declared_context=65536,
        certified_context=32768,
        roles={"coder"},
        status=HarnessStatus.VERIFIED,
        performance=ModelPerformance(
            task_quality=quality,
            tool_success=quality,
            schema_success=quality,
            test_pass_after_patch=quality,
            reviewer_acceptance=quality,
            stability=quality,
            generation_tps=30,
        ),
    )


def test_router_uses_capability_and_quality() -> None:
    registry = ModelRegistry([make_model("weak", 0.4, True), make_model("strong", 0.9, True)])
    decision = ModelRouter(registry).route(
        RouteRequest(
            required_capabilities=frozenset({Capability.CHAT, Capability.TOOLS}),
            role="coder",
        )
    )
    assert decision.model.key == "strong"

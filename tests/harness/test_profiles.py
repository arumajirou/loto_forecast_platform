from __future__ import annotations

from loto.harness.contracts import ChatRequest, EngineKind, Message, ModelDescriptor
from loto.harness.profiles import ProfileRegistry


def descriptor(key: str, architecture: str | None = None) -> ModelDescriptor:
    return ModelDescriptor(
        key=key,
        engine=EngineKind.LMSTUDIO,
        endpoint="http://127.0.0.1:1234",
        architecture=architecture,
    )


def request(task_type: str = "chat") -> ChatRequest:
    return ChatRequest(
        model="qwen3-coder-30b-a3b-instruct",
        messages=[Message(role="user", content="Solve this task")],
        task_type=task_type,
    )


def test_qwen_coder_quality_profile_uses_non_thinking_only_mode() -> None:
    registry = ProfileRegistry()
    applied = registry.apply(
        request(),
        descriptor("qwen3-coder-30b-a3b-instruct"),
        mode="quality",
    )
    assert applied.profile_id == "qwen3"
    assert applied.request.temperature == 0.7
    assert applied.request.top_p == 0.8
    assert applied.request.top_k == 20
    assert "/think" not in applied.request.messages[-1].content
    assert "/no_think" not in applied.request.messages[-1].content
    assert applied.request.extra_body["repetition_penalty"] == 1.05
    assert applied.request.metadata["thinking_mode_supported"] is False
    assert "thinking_mode=non_thinking_only" in applied.changes
    assert applied.request.metadata["profile_id"] == "qwen3"


def test_qwen_reasoning_profile_avoids_greedy_sampling() -> None:
    registry = ProfileRegistry()
    applied = registry.apply(
        request("reasoning"),
        descriptor("local-alias", architecture="qwen3moe"),
        mode="reasoning",
    )
    assert applied.request.temperature == 0.6
    assert applied.request.top_p == 0.95
    assert applied.request.messages[-1].content.endswith("/think")
    assert applied.request.metadata["thinking_mode_supported"] is True



def test_qwen_coder_reasoning_uses_verification_cue_without_think_switch() -> None:
    applied = ProfileRegistry().apply(
        request("reasoning"),
        descriptor("qwen3-coder-30b-a3b-instruct"),
        mode="reasoning",
    )
    content = applied.request.messages[-1].content
    assert "/think" not in content
    assert "Double-check every arithmetic operation" in content
    assert applied.request.temperature == 0.7
    assert applied.request.top_p == 0.8
    assert applied.request.extra_body["repetition_penalty"] == 1.05


def test_gemini_profile_resolution() -> None:
    model = ModelDescriptor(
        key="gemini-3.6-flash",
        engine=EngineKind.GEMINI,
        endpoint="https://generativelanguage.googleapis.com",
        provider="google",
    )
    applied = ProfileRegistry().apply(
        ChatRequest(
            model=model.key,
            messages=[Message(role="user", content="Use a tool")],
            task_type="tools",
        ),
        model,
        mode="tools",
    )
    assert applied.profile_id == "gemini-interactions"
    assert applied.request.tool_choice is not None
    assert applied.request.extra_body["thinking_level"] == "medium"
    assert applied.request.metadata["sampling_parameters_supported"] is False
    assert "sampling_parameters=omitted" in applied.changes
    assert "preserve_agent_state" in applied.expected_effects


def test_gemini_3_6_reasoning_profile_uses_thinking_level_only() -> None:
    model = ModelDescriptor(
        key="gemini-3.6-flash",
        engine=EngineKind.GEMINI,
        endpoint="https://generativelanguage.googleapis.com",
        provider="google",
    )
    applied = ProfileRegistry().apply(
        ChatRequest(
            model=model.key,
            messages=[Message(role="user", content="Solve carefully")],
            task_type="reasoning",
            temperature=0.2,
            top_p=0.9,
            top_k=40,
        ),
        model,
        mode="reasoning",
    )
    assert applied.request.extra_body["thinking_level"] == "high"
    assert applied.request.metadata["sampling_parameters_supported"] is False
    payload = __import__(
        "loto.harness.engines.gemini",
        fromlist=["GeminiEngine"],
    ).GeminiEngine._payload(applied.request)
    generation_config = payload["generation_config"]
    assert generation_config["thinking_level"] == "high"
    assert "temperature" not in generation_config
    assert "top_p" not in generation_config
    assert "top_k" not in generation_config


def test_kat_coder_profile_resolves_before_generic_qwen() -> None:
    model = descriptor(
        "kwaipilot_kat-coder-v2.5-dev",
        architecture="qwen35moe",
    )
    applied = ProfileRegistry().apply(
        ChatRequest(
            model=model.key,
            messages=[Message(role="user", content="Fix the repository")],
            task_type="coding",
        ),
        model,
        mode="quality",
    )
    assert applied.profile_id == "kat-coder-v2.5"
    assert applied.request.temperature == 1.0
    assert applied.request.top_p == 0.95
    assert applied.request.presence_penalty == 1.5
    assert applied.request.extra_body["top_k"] == 20
    kwargs = applied.request.extra_body["chat_template_kwargs"]
    assert kwargs["preserve_thinking"] is True
    assert applied.request.metadata["thinking_enabled"] is True


def test_kat_coder_fast_mode_disables_thinking_via_template_kwargs() -> None:
    model = descriptor("kwaipilot_kat-coder-v2.5-dev")
    applied = ProfileRegistry().apply(
        ChatRequest(
            model=model.key,
            messages=[Message(role="user", content="Return JSON")],
            task_type="structured",
        ),
        model,
        mode="fast",
    )
    kwargs = applied.request.extra_body["chat_template_kwargs"]
    assert kwargs["enable_thinking"] is False
    assert applied.request.temperature == 0.7
    assert applied.request.top_p == 0.8
    assert applied.request.metadata["thinking_enabled"] is False

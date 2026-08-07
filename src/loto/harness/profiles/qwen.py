from __future__ import annotations

from ..contracts import ChatRequest, ModelDescriptor
from .base import ModelProfile, ProfileApplication, append_switch_to_last_user


def _supports_hybrid_thinking(descriptor: ModelDescriptor) -> bool:
    """Return whether the concrete Qwen model supports /think and /no_think.

    Qwen3-Coder instruct models are non-thinking-only. Generic Qwen3 chat models may
    support hybrid thinking. Keep this fail-closed: an explicit coder marker disables
    soft thinking switches instead of assuming that every qwen3 architecture supports
    them.
    """

    identity = " ".join(
        value.lower()
        for value in (descriptor.key, descriptor.architecture or "")
        if value
    )
    return "qwen3-coder" not in identity and "qwen3coder" not in identity


class QwenProfile(ModelProfile):
    def __init__(self) -> None:
        super().__init__(
            profile_id="qwen3",
            family="qwen",
            patterns=("qwen*", "*qwen*", "qwen3*", "qwen35*", "qwen3moe*"),
            default_mode="quality",
            supported_modes=("generic", "fast", "quality", "reasoning", "tools"),
            notes=(
                "Qwen3-Coder instruct models are non-thinking-only",
                "hybrid Qwen3 chat models may use /think and /no_think",
                "tool results must remain in history for multi-step tool use",
                "thinking content must not be silently discarded when a model exposes it",
            ),
        )

    def apply(
        self,
        request: ChatRequest,
        descriptor: ModelDescriptor,
        *,
        mode: str = "auto",
        task_type: str | None = None,
    ) -> ProfileApplication:
        base = super().apply(
            request,
            descriptor,
            mode=mode,
            task_type=task_type,
        )
        selected = base.mode
        if selected == "generic":
            return base

        changes: list[str] = []
        effects: list[str] = []
        update: dict[str, object] = {}
        extra = dict(base.request.extra_body)
        hybrid_thinking = _supports_hybrid_thinking(descriptor)
        requested_reasoning = selected == "reasoning" or base.task_type == "reasoning"

        if hybrid_thinking:
            switch = "/think" if requested_reasoning else "/no_think"
            update["messages"] = append_switch_to_last_user(base.request.messages, switch)
            changes.append(f"soft_switch={switch}")
            if requested_reasoning:
                update.update(
                    {
                        "temperature": 0.6,
                        "top_p": 0.95,
                        "top_k": 20,
                        "min_p": 0.0,
                    }
                )
                effects.extend(
                    ("reduce_reasoning_repetition", "improve_complex_reasoning")
                )
            else:
                update.update(
                    {
                        "temperature": 0.7,
                        "top_p": 0.8,
                        "top_k": 20,
                        "min_p": 0.0,
                    }
                )
                effects.extend(("reduce_latency", "reduce_unwanted_thinking"))
        else:
            # Qwen3-Coder is non-thinking-only. Do not append unsupported soft switches.
            # Use the model-card sampling baseline and add only a lightweight verification
            # cue for reasoning tasks.
            update.update(
                {
                    "temperature": 0.7,
                    "top_p": 0.8,
                    "top_k": 20,
                    "min_p": 0.0,
                }
            )
            extra["repetition_penalty"] = 1.05
            changes.extend(
                (
                    "thinking_mode=non_thinking_only",
                    "repetition_penalty=1.05",
                )
            )
            effects.extend(("use_supported_qwen3_coder_mode", "avoid_invalid_think_switch"))
            if requested_reasoning:
                update["messages"] = append_switch_to_last_user(
                    base.request.messages,
                    (
                        "Double-check every arithmetic operation before producing the "
                        "requested final format."
                    ),
                )
                changes.append("reasoning_cue=double_check")
                effects.append("improve_non_thinking_reasoning_accuracy")

        if selected == "fast":
            update.update(
                {
                    "temperature": 0.3,
                    "top_p": 0.8,
                    "max_tokens": min(1024, base.request.max_tokens),
                }
            )
            effects.append("lower_output_cost")
        elif selected == "tools" or base.task_type == "tools":
            update.update(
                {
                    "temperature": 0.2,
                    "tool_choice": base.request.tool_choice or "auto",
                }
            )
            effects.append("increase_tool_call_determinism")

        extra["top_k"] = update.get("top_k", base.request.top_k)
        extra["min_p"] = update.get("min_p", base.request.min_p)
        update["extra_body"] = {
            key: value for key, value in extra.items() if value is not None
        }
        metadata = dict(base.request.metadata)
        metadata["thinking_mode_supported"] = hybrid_thinking
        update["metadata"] = metadata
        updated = base.request.model_copy(update=update)
        return ProfileApplication(
            profile_id=base.profile_id,
            family=base.family,
            mode=base.mode,
            task_type=base.task_type,
            request=updated,
            changes=tuple(changes),
            expected_effects=tuple(effects),
        )

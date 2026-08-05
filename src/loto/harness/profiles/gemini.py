from __future__ import annotations

from ..contracts import ChatRequest, ModelDescriptor
from .base import ModelProfile, ProfileApplication


def _uses_modern_gemini_3_config(descriptor: ModelDescriptor) -> bool:
    key = descriptor.key.lower()
    return key.startswith("gemini-3.6-") or key.startswith("gemini-3.5-flash-lite")


class GeminiProfile(ModelProfile):
    def __init__(self) -> None:
        super().__init__(
            profile_id="gemini-interactions",
            family="gemini",
            patterns=("gemini*", "google:gemini*"),
            default_mode="quality",
            supported_modes=("generic", "fast", "quality", "reasoning", "tools", "structured"),
            notes=(
                "uses Gemini Interactions API semantics",
                "function results and thought steps must be preserved exactly in stateless mode",
                "stable model IDs are preferred for production",
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
        base = super().apply(request, descriptor, mode=mode, task_type=task_type)
        if base.mode == "generic":
            return base
        update: dict[str, object] = {}
        changes: list[str] = ["api=interactions"]
        effects: list[str] = ["preserve_agent_state"]
        modern_gemini_3 = _uses_modern_gemini_3_config(descriptor)

        if modern_gemini_3:
            thinking_level = "medium"
            if base.mode == "fast":
                thinking_level = "minimal"
                update["max_tokens"] = min(1024, base.request.max_tokens)
                effects.extend(("reduce_latency", "reduce_cost"))
            elif base.mode == "reasoning" or base.task_type == "reasoning":
                thinking_level = "high"
                effects.append("increase_reasoning_depth")
            elif base.mode == "tools" or base.task_type == "tools":
                thinking_level = "medium"
                update["tool_choice"] = base.request.tool_choice or "required"
                effects.append("increase_function_schema_adherence")
            elif base.mode == "structured" or base.task_type == "structured":
                thinking_level = "low"
                effects.append("increase_structured_output_stability")
            update["extra_body"] = {
                **base.request.extra_body,
                "thinking_level": thinking_level,
            }
            update["metadata"] = {
                **base.request.metadata,
                "sampling_parameters_supported": False,
                "thinking_level": thinking_level,
            }
            changes.extend(
                (
                    "sampling_parameters=omitted",
                    f"thinking_level={thinking_level}",
                )
            )
        else:
            if base.mode == "fast":
                update.update(
                    {
                        "temperature": 0.2,
                        "top_p": 0.8,
                        "max_tokens": min(1024, base.request.max_tokens),
                    }
                )
                effects.extend(("reduce_latency", "reduce_cost"))
            elif base.mode == "reasoning" or base.task_type == "reasoning":
                update.update({"temperature": 0.7, "top_p": 0.95})
                update["extra_body"] = {
                    **base.request.extra_body,
                    "thinking_level": "high",
                }
                effects.append("increase_reasoning_depth")
            elif base.mode == "tools" or base.task_type == "tools":
                update["tool_choice"] = base.request.tool_choice or "required"
                effects.append("increase_function_schema_adherence")
            elif base.mode == "structured" or base.task_type == "structured":
                update["temperature"] = 0.1
                effects.append("increase_structured_output_stability")
            else:
                update.update({"temperature": 0.4, "top_p": 0.9})

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

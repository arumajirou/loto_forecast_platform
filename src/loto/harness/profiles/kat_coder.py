from __future__ import annotations

from ..contracts import ChatRequest, ModelDescriptor
from .base import ModelProfile, ProfileApplication


class KatCoderProfile(ModelProfile):
    """KAT-Coder-V2.5-Dev profile based on the official model contract.

    The model thinks by default. Direct/non-thinking responses are selected with
    ``chat_template_kwargs.enable_thinking=False`` rather than prompt suffixes.
    Historical thinking can be preserved for agentic multi-turn work.
    """

    def __init__(self) -> None:
        super().__init__(
            profile_id="kat-coder-v2.5",
            family="kat-coder",
            patterns=(
                "*kat-coder-v2.5*",
                "*kat_coder-v2.5*",
                "*kwaipilot*kat-coder*",
            ),
            default_mode="quality",
            supported_modes=(
                "generic",
                "fast",
                "quality",
                "reasoning",
                "tools",
                "structured",
            ),
            notes=(
                "thinking is enabled by default",
                "non-thinking uses chat_template_kwargs.enable_thinking=false",
                "agentic turns may preserve historical thinking traces",
                "tool use expects a qwen3_coder-compatible tool-call parser",
                "native context is 262144 tokens; local certification remains required",
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
        if base.mode == "generic":
            return base

        selected = base.mode
        task = base.task_type
        extra = dict(base.request.extra_body)
        chat_template_kwargs = dict(extra.get("chat_template_kwargs") or {})
        changes: list[str] = []
        effects: list[str] = []
        update: dict[str, object] = {
            "presence_penalty": 1.5,
            "top_k": 20,
        }

        direct_mode = selected in {"fast", "structured"} or task == "structured"
        if direct_mode:
            update.update(
                {
                    "temperature": 0.7,
                    "top_p": 0.8,
                }
            )
            chat_template_kwargs["enable_thinking"] = False
            changes.append("thinking_mode=disabled_via_chat_template_kwargs")
            effects.extend(("reduce_latency", "improve_output_contract_compliance"))
        else:
            update.update(
                {
                    "temperature": 1.0,
                    "top_p": 0.95,
                }
            )
            chat_template_kwargs["preserve_thinking"] = True
            changes.append("thinking_mode=default_enabled")
            changes.append("preserve_thinking=true")
            effects.extend(("improve_agentic_reasoning", "reuse_historical_reasoning"))

        if selected == "tools" or task == "tools":
            update["tool_choice"] = base.request.tool_choice or "auto"
            effects.append("improve_agentic_tool_use")
        if selected == "fast":
            update["max_tokens"] = min(1024, base.request.max_tokens)
            effects.append("lower_output_cost")

        extra["top_k"] = 20
        extra["chat_template_kwargs"] = chat_template_kwargs
        update["extra_body"] = extra

        metadata = dict(base.request.metadata)
        metadata.update(
            {
                "thinking_mode_supported": True,
                "thinking_enabled": not direct_mode,
                "preserve_thinking": bool(chat_template_kwargs.get("preserve_thinking")),
                "official_profile_contract": "KAT-Coder-V2.5-Dev",
            }
        )
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

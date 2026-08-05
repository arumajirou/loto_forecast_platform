from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any

from ..contracts import ChatRequest, Message, ModelDescriptor


@dataclass(frozen=True)
class ProfileApplication:
    profile_id: str
    family: str
    mode: str
    task_type: str
    request: ChatRequest
    changes: tuple[str, ...] = ()
    expected_effects: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelProfile:
    profile_id: str
    family: str
    patterns: tuple[str, ...]
    default_mode: str = "quality"
    supported_modes: tuple[str, ...] = ("fast", "quality")
    notes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def matches(self, descriptor: ModelDescriptor) -> bool:
        values = [descriptor.key.lower()]
        if descriptor.architecture:
            values.append(descriptor.architecture.lower())
        if descriptor.provider:
            values.append(descriptor.provider.lower())
        for pattern in self.patterns:
            normalized = pattern.lower()
            if any(fnmatch(value, normalized) for value in values):
                return True
        return False

    def apply(
        self,
        request: ChatRequest,
        descriptor: ModelDescriptor,
        *,
        mode: str = "auto",
        task_type: str | None = None,
    ) -> ProfileApplication:
        selected_mode = self.default_mode if mode == "auto" else mode
        if selected_mode not in self.supported_modes:
            raise ValueError(
                f"profile {self.profile_id} does not support mode {selected_mode}; "
                f"allowed={','.join(self.supported_modes)}"
            )
        selected_task = task_type or request.task_type
        updated = request.model_copy(
            update={
                "profile_mode": selected_mode,
                "task_type": selected_task,
                "metadata": {
                    **request.metadata,
                    "profile_id": self.profile_id,
                    "model_family": self.family,
                },
            }
        )
        return ProfileApplication(
            profile_id=self.profile_id,
            family=self.family,
            mode=selected_mode,
            task_type=selected_task,
            request=updated,
        )


def append_switch_to_last_user(messages: list[Message], switch: str) -> list[Message]:
    updated = [message.model_copy() for message in messages]
    for index in range(len(updated) - 1, -1, -1):
        if updated[index].role == "user":
            content = updated[index].content.rstrip()
            if switch not in content:
                updated[index] = updated[index].model_copy(
                    update={"content": f"{content}\n\n{switch}"}
                )
            break
    return updated

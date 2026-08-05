from __future__ import annotations

from ..contracts import ChatRequest, ModelDescriptor
from .base import ModelProfile, ProfileApplication
from .gemini import GeminiProfile
from .generic import GenericProfile
from .kat_coder import KatCoderProfile
from .qwen import QwenProfile


class ProfileRegistry:
    def __init__(self, profiles: list[ModelProfile] | None = None) -> None:
        self.profiles = profiles or [
            KatCoderProfile(),
            QwenProfile(),
            GeminiProfile(),
            GenericProfile(),
        ]

    def resolve(self, descriptor: ModelDescriptor) -> ModelProfile:
        if descriptor.profile_id:
            for profile in self.profiles:
                if profile.profile_id == descriptor.profile_id:
                    return profile
            raise ValueError(f"unknown model profile: {descriptor.profile_id}")
        for profile in self.profiles:
            if profile.profile_id != "generic-openai" and profile.matches(descriptor):
                return profile
        return next(profile for profile in self.profiles if profile.profile_id == "generic-openai")

    def apply(
        self,
        request: ChatRequest,
        descriptor: ModelDescriptor,
        *,
        mode: str = "auto",
        task_type: str | None = None,
    ) -> ProfileApplication:
        return self.resolve(descriptor).apply(
            request,
            descriptor,
            mode=mode,
            task_type=task_type,
        )

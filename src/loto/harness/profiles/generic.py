from __future__ import annotations

from .base import ModelProfile


class GenericProfile(ModelProfile):
    def __init__(self) -> None:
        super().__init__(
            profile_id="generic-openai",
            family="generic",
            patterns=("*",),
            default_mode="generic",
            supported_modes=("generic", "fast", "quality", "tools", "structured"),
        )

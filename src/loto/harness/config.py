from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from .contracts import ModelDescriptor
from .errors import ConfigurationError


class ContextSettings(BaseModel):
    total_tokens: int = 65536
    exact_source_tokens: int = 32768
    retrieved_memory_tokens: int = 8192
    conversation_summary_tokens: int = 8192
    tool_result_tokens: int = 4096
    output_reserve_tokens: int = 8192
    safety_reserve_tokens: int = 4096
    emergency_threshold: float = Field(default=0.85, gt=0, le=1)
    uncertified_native_cap_tokens: int = Field(default=32768, ge=4096)

    def validate_budget(self) -> None:
        allocated = (
            self.exact_source_tokens
            + self.retrieved_memory_tokens
            + self.conversation_summary_tokens
            + self.tool_result_tokens
            + self.output_reserve_tokens
            + self.safety_reserve_tokens
        )
        if allocated != self.total_tokens:
            raise ConfigurationError(
                f"context token budget must total {self.total_tokens}, got {allocated}"
            )


class SecuritySettings(BaseModel):
    allowed_roots: list[str] = Field(default_factory=list)
    command_timeout_seconds: int = Field(default=300, ge=1)
    max_request_bytes: int = Field(default=16 * 1024 * 1024, ge=1024)
    max_context_items: int = Field(default=128, ge=1, le=4096)
    max_context_item_chars: int = Field(default=500_000, ge=1)
    max_context_total_chars: int = Field(default=4_000_000, ge=1)
    redact_environment_names: list[str] = Field(
        default_factory=lambda: [
            "TOKEN",
            "KEY",
            "SECRET",
            "PASSWORD",
            "COOKIE",
            "CREDENTIAL",
        ]
    )


class HarnessSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=17200, ge=1, le=65535)
    models: list[ModelDescriptor] = Field(default_factory=list)
    context: ContextSettings = Field(default_factory=ContextSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    memory_database_url: str = "sqlite:///artifacts/harness/memory.sqlite3"
    artifact_root: str = "artifacts/harness"

    @field_validator("host")
    @classmethod
    def safe_default_host(cls, value: str) -> str:
        if value == "0.0.0.0" and os.getenv("HARNESS_ALLOW_PUBLIC_BIND") != "1":
            raise ValueError(
                "public binding requires HARNESS_ALLOW_PUBLIC_BIND=1; use 127.0.0.1 by default"
            )
        return value

    @staticmethod
    def _resolve_allowed_root(value: str, *, config_dir: Path) -> str:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = config_dir / candidate
        return str(candidate.resolve())

    @classmethod
    def from_yaml(cls, path: str | Path) -> HarnessSettings:
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise ConfigurationError(f"configuration not found: {source}")
        raw: dict[str, Any] = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        settings = cls.model_validate(raw)
        settings.context.validate_budget()
        normalized_roots = [
            cls._resolve_allowed_root(value, config_dir=source.parent)
            for value in settings.security.allowed_roots
        ]
        settings = settings.model_copy(
            update={
                "security": settings.security.model_copy(update={"allowed_roots": normalized_roots})
            }
        )
        return settings

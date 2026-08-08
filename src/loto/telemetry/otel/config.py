"""Strict OpenTelemetry runtime configuration."""

from __future__ import annotations

import re
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RESOURCE_KEY_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")


class OtlpProtocol(StrEnum):
    GRPC = "grpc"
    HTTP_PROTOBUF = "http/protobuf"


class TracingRuntimeStatus(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_PROBED = "NOT_PROBED"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    VERIFIED = "VERIFIED"


class TracingConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
        allow_inf_nan=False,
    )

    enabled: bool = False
    service_name: str = "loto-forecast-platform"
    service_version: str = "UNPINNED"
    environment: str = "development"
    otlp_endpoint: str | None = None
    otlp_protocol: OtlpProtocol = OtlpProtocol.GRPC
    export_timeout_seconds: float = Field(default=5.0, gt=0.0, le=60.0)
    batch_queue_size: int = Field(default=2048, ge=64, le=65536)
    batch_size: int = Field(default=512, ge=1, le=8192)
    sample_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    resource_attributes: dict[str, str | bool | int | float] = Field(default_factory=dict)
    instrument_fastapi: bool = True
    instrument_httpx: bool = True
    instrument_sqlalchemy: bool = True

    @field_validator("service_name", "service_version", "environment")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not _NAME_RE.fullmatch(value):
            raise ValueError(
                "service identity contains unsafe characters or exceeds 128 characters"
            )
        return value

    @field_validator("otlp_endpoint")
    @classmethod
    def validate_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("otlp_endpoint must be an absolute http(s) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("otlp_endpoint must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("otlp_endpoint must not contain query or fragment data")
        return value.rstrip("/")

    @field_validator("resource_attributes")
    @classmethod
    def validate_resource_attributes(
        cls, value: dict[str, str | bool | int | float]
    ) -> dict[str, str | bool | int | float]:
        if len(value) > 32:
            raise ValueError("resource_attributes exceed 32 entries")
        for key, item in value.items():
            if not _RESOURCE_KEY_RE.fullmatch(key):
                raise ValueError(f"invalid resource attribute key: {key!r}")
            if any(part in key for part in ("password", "secret", "token", "authorization")):
                raise ValueError(f"sensitive resource attribute key is prohibited: {key}")
            if isinstance(item, str) and len(item) > 256:
                raise ValueError(f"resource attribute {key!r} exceeds 256 characters")
        return value

    @model_validator(mode="after")
    def validate_batch(self) -> TracingConfig:
        if self.batch_size > self.batch_queue_size:
            raise ValueError("batch_size must not exceed batch_queue_size")
        return self

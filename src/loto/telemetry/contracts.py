"""Strict telemetry event envelope and bounded semantic enums."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from loto.telemetry.redaction import (
    PROTECTED_ACTUAL,
    REDACTED,
    RevealState,
    is_protected_actual_key,
    is_sensitive_key,
)

_EVENT_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._][a-z0-9]+){1,7}$")
_ATTRIBUTE_KEY_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")

MAX_ATTRIBUTE_KEYS = 32
MAX_ATTRIBUTE_BYTES = 4096
MAX_ATTRIBUTE_DEPTH = 6


class Severity(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Component(StrEnum):
    API = "api"
    ORCHESTRATOR = "orchestrator"
    FORECAST_WORKER = "forecast_worker"
    DATA_PIPELINE = "data_pipeline"
    EVALUATION = "evaluation"
    HPO = "hpo"
    REGISTRY = "registry"
    ARTIFACT = "artifact"
    RUNTIME_CERTIFICATION = "runtime_certification"
    SCHEDULER = "scheduler"
    TELEMETRY = "telemetry"


class Stage(StrEnum):
    RECEIVE = "RECEIVE"
    DATA_LOAD = "DATA_LOAD"
    DATA_VALIDATE = "DATA_VALIDATE"
    SPLIT_CREATE = "SPLIT_CREATE"
    FEATURE_FIT = "FEATURE_FIT"
    FEATURE_TRANSFORM = "FEATURE_TRANSFORM"
    HPO_STUDY = "HPO_STUDY"
    HPO_TRIAL = "HPO_TRIAL"
    MODEL_LOAD = "MODEL_LOAD"
    FIT = "FIT"
    PREDICT = "PREDICT"
    PREDICTION_LOCK = "PREDICTION_LOCK"
    ACTUAL_READ = "ACTUAL_READ"
    SCORE = "SCORE"
    ARTIFACT_PERSIST = "ARTIFACT_PERSIST"
    REGISTRY_PERSIST = "REGISTRY_PERSIST"
    PROMOTION_EVALUATE = "PROMOTION_EVALUATE"
    HEALTH = "HEALTH"
    TELEMETRY = "TELEMETRY"


class EventStatus(StrEnum):
    STARTED = "STARTED"
    PASS = "PASS"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    DROPPED = "DROPPED"


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    TIMEOUT = "TIMEOUT"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    NONFINITE_OUTPUT = "NONFINITE_OUTPUT"
    CPU_FALLBACK = "CPU_FALLBACK"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"
    REDACTION_FAILURE = "REDACTION_FAILURE"
    SINK_UNAVAILABLE = "SINK_UNAVAILABLE"
    BUFFER_FULL = "BUFFER_FULL"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class StrictTelemetryModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
        allow_inf_nan=False,
    )


def _validate_attribute_value(value: Any, *, depth: int = 0) -> None:
    if depth > MAX_ATTRIBUTE_DEPTH:
        raise ValueError(f"attribute nesting exceeds {MAX_ATTRIBUTE_DEPTH}")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("attributes cannot contain NaN or Infinity")
        return
    if isinstance(value, list):
        for item in value:
            _validate_attribute_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("attribute object keys must be strings")
            _validate_attribute_value(child, depth=depth + 1)
        return
    raise ValueError(f"unsupported telemetry attribute type: {type(value).__name__}")


def _validate_redaction_state(
    value: Any,
    *,
    key: str | None,
    reveal_state: RevealState,
) -> None:
    if key is not None and is_sensitive_key(key) and value != REDACTED:
        raise ValueError(f"sensitive attribute {key!r} was not redacted")
    if (
        key is not None
        and is_protected_actual_key(key)
        and reveal_state is not RevealState.AUTHORIZED
        and value not in (PROTECTED_ACTUAL, REDACTED)
    ):
        raise ValueError(f"protected actual attribute {key!r} was not redacted")
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _validate_redaction_state(
                child_value,
                key=child_key,
                reveal_state=reveal_state,
            )
    elif isinstance(value, list):
        for child_value in value:
            _validate_redaction_state(
                child_value,
                key=None,
                reveal_state=reveal_state,
            )


class TelemetryEvent(StrictTelemetryModel):
    """One safe, structured, correlation-ready telemetry event."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    timestamp_utc: AwareDatetime
    severity: Severity
    event_name: str = Field(min_length=3, max_length=96)
    component: Component
    status: EventStatus
    run_id: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    game_id: str | None = Field(default=None, max_length=64)
    model_id: str | None = Field(default=None, max_length=128)
    model_revision: str | None = Field(default=None, max_length=128)
    stage: Stage | None = None
    fold_id: int | None = Field(default=None, ge=0)
    seed: int | None = None
    duration_ms: float | None = Field(default=None, ge=0.0)
    error_code: ErrorCode | None = None
    reveal_state: RevealState = RevealState.PROTECTED
    attributes: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("timestamp_utc")
    @classmethod
    def validate_timestamp_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("timestamp_utc must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, value: str) -> str:
        if not _EVENT_NAME_RE.fullmatch(value):
            raise ValueError("event_name must use bounded lowercase dot/underscore segments")
        return value

    @field_validator("run_id", "request_id")
    @classmethod
    def validate_correlation_id(cls, value: str | None) -> str | None:
        if value is not None and not _ID_RE.fullmatch(value):
            raise ValueError("run_id/request_id contains unsafe characters or exceeds 128 chars")
        return value

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id(cls, value: str | None) -> str | None:
        if value is not None and not _TRACE_ID_RE.fullmatch(value):
            raise ValueError("trace_id must be 32 lowercase hexadecimal characters")
        return value

    @field_validator("span_id")
    @classmethod
    def validate_span_id(cls, value: str | None) -> str | None:
        if value is not None and not _SPAN_ID_RE.fullmatch(value):
            raise ValueError("span_id must be 16 lowercase hexadecimal characters")
        return value

    @field_validator("attributes")
    @classmethod
    def validate_attributes(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if len(value) > MAX_ATTRIBUTE_KEYS:
            raise ValueError(f"attributes exceed {MAX_ATTRIBUTE_KEYS} keys")
        for key, child in value.items():
            if not _ATTRIBUTE_KEY_RE.fullmatch(key):
                raise ValueError(f"invalid attribute key: {key!r}")
            _validate_attribute_value(child)
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_ATTRIBUTE_BYTES:
            raise ValueError(f"attributes exceed {MAX_ATTRIBUTE_BYTES} serialized bytes")
        return value

    @model_validator(mode="after")
    def validate_redaction(self) -> TelemetryEvent:
        _validate_redaction_state(
            self.attributes,
            key=None,
            reveal_state=self.reveal_state,
        )
        return self

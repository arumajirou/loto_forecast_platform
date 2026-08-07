"""Strict, exporter-neutral telemetry contract foundation."""

from loto.telemetry.buffer import (
    BoundedTelemetryBuffer,
    EmitResult,
    EmitStatus,
    EventImportance,
)
from loto.telemetry.codec import encode_event_json, event_sha256
from loto.telemetry.context import (
    TelemetryContext,
    bind_telemetry_context,
    current_telemetry_context,
)
from loto.telemetry.contracts import (
    Component,
    ErrorCode,
    EventStatus,
    Severity,
    Stage,
    TelemetryEvent,
)
from loto.telemetry.factory import build_event
from loto.telemetry.metrics import (
    PROHIBITED_LABELS,
    MetricDefinition,
    MetricKind,
    MetricRegistry,
    default_telemetry_metric_registry,
)
from loto.telemetry.redaction import (
    PROTECTED_ACTUAL,
    REDACTED,
    RevealState,
    redact_mapping,
    redact_string,
    redact_value,
)

__all__ = [
    "BoundedTelemetryBuffer",
    "Component",
    "EmitResult",
    "EmitStatus",
    "ErrorCode",
    "EventImportance",
    "EventStatus",
    "MetricDefinition",
    "MetricKind",
    "MetricRegistry",
    "PROHIBITED_LABELS",
    "PROTECTED_ACTUAL",
    "REDACTED",
    "RevealState",
    "Severity",
    "Stage",
    "TelemetryContext",
    "TelemetryEvent",
    "bind_telemetry_context",
    "build_event",
    "current_telemetry_context",
    "default_telemetry_metric_registry",
    "encode_event_json",
    "event_sha256",
    "redact_mapping",
    "redact_string",
    "redact_value",
]

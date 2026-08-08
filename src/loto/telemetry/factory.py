"""Safe event construction that applies correlation and redaction first."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from loto.telemetry.context import current_telemetry_context
from loto.telemetry.contracts import (
    Component,
    ErrorCode,
    EventStatus,
    Severity,
    Stage,
    TelemetryEvent,
)
from loto.telemetry.redaction import RevealState, redact_mapping


def build_event(
    event_name: str,
    *,
    component: Component,
    status: EventStatus,
    severity: Severity = Severity.INFO,
    stage: Stage | None = None,
    attributes: Mapping[str, Any] | None = None,
    reveal_state: RevealState = RevealState.PROTECTED,
    timestamp_utc: datetime | None = None,
    duration_ms: float | None = None,
    error_code: ErrorCode | None = None,
    exception: BaseException | None = None,
    **identity_overrides: object,
) -> TelemetryEvent:
    """Build one strict event; exception text is never retained."""

    context = current_telemetry_context().as_dict()
    allowed_overrides = {
        "run_id",
        "request_id",
        "trace_id",
        "span_id",
        "game_id",
        "model_id",
        "model_revision",
        "fold_id",
        "seed",
    }
    unknown = set(identity_overrides).difference(allowed_overrides)
    if unknown:
        raise ValueError(f"unknown event identity fields: {sorted(unknown)}")
    context.update(identity_overrides)
    safe_attributes = dict(attributes or {})
    if exception is not None:
        safe_attributes["exception_type"] = type(exception).__name__
        error_code = error_code or ErrorCode.UNKNOWN_ERROR
    safe_attributes = redact_mapping(safe_attributes, reveal_state=reveal_state)
    return TelemetryEvent.model_validate(
        {
            "timestamp_utc": timestamp_utc or datetime.now(UTC),
            "severity": severity,
            "event_name": event_name,
            "component": component,
            "status": status,
            "stage": stage,
            "duration_ms": duration_ms,
            "error_code": error_code,
            "reveal_state": reveal_state,
            "attributes": safe_attributes,
            **context,
        }
    )

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from loto.telemetry import (
    BoundedTelemetryBuffer,
    Component,
    EmitStatus,
    ErrorCode,
    EventImportance,
    EventStatus,
    MetricDefinition,
    MetricKind,
    MetricRegistry,
    PROTECTED_ACTUAL,
    REDACTED,
    RevealState,
    Severity,
    Stage,
    TelemetryEvent,
    bind_telemetry_context,
    build_event,
    current_telemetry_context,
    default_telemetry_metric_registry,
    encode_event_json,
    event_sha256,
    redact_mapping,
)

NOW = datetime(2026, 8, 6, tzinfo=timezone.utc)


def _event(**updates: object) -> TelemetryEvent:
    payload: dict[str, object] = {
        "timestamp_utc": NOW,
        "severity": Severity.INFO,
        "event_name": "model.predict.completed",
        "component": Component.FORECAST_WORKER,
        "status": EventStatus.PASS,
        "stage": Stage.PREDICT,
        "attributes": {},
    }
    payload.update(updates)
    return TelemetryEvent.model_validate(payload)


def test_event_contract_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        _event(unknown=True)


def test_timestamp_is_normalized_to_utc_and_naive_is_rejected() -> None:
    event = _event(timestamp_utc=NOW.astimezone(timezone(timedelta(hours=9))))
    assert event.timestamp_utc.utcoffset() == timedelta(0)
    with pytest.raises(ValidationError):
        _event(timestamp_utc=datetime(2026, 8, 6))


@pytest.mark.parametrize("event_name", ["Predict", "predict", "model predict", "model..predict"])
def test_event_name_is_bounded_and_structured(event_name: str) -> None:
    with pytest.raises(ValidationError):
        _event(event_name=event_name)


def test_correlation_identifiers_are_strict_and_trace_span_are_distinct() -> None:
    event = _event(
        run_id="run-1",
        request_id="request-1",
        trace_id="a" * 32,
        span_id="b" * 16,
    )
    assert event.request_id != event.trace_id
    with pytest.raises(ValidationError):
        _event(trace_id="short")


def test_nonfinite_duration_and_attributes_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _event(duration_ms=float("nan"))
    with pytest.raises(ValidationError):
        _event(attributes={"metric": float("inf")})


def test_attribute_count_and_serialized_size_are_bounded() -> None:
    with pytest.raises(ValidationError):
        _event(attributes={f"key_{index}": index for index in range(33)})
    with pytest.raises(ValidationError):
        _event(attributes={"payload": "x" * 5000})


def test_direct_contract_rejects_unredacted_secret_and_actual() -> None:
    with pytest.raises(ValidationError):
        _event(attributes={"api_key": "secret"})
    with pytest.raises(ValidationError):
        _event(attributes={"actuals": [1, 2, 3]})


def test_direct_contract_rejects_nested_unredacted_secret() -> None:
    with pytest.raises(ValidationError):
        _event(attributes={"nested": {"database_url": "postgresql://u:p@db/app"}})


def test_authorized_reveal_state_allows_actual_value_after_governed_reveal() -> None:
    event = build_event(
        "evaluation.actual.read",
        component=Component.EVALUATION,
        status=EventStatus.PASS,
        stage=Stage.ACTUAL_READ,
        attributes={"actuals": [1, 2, 3]},
        reveal_state=RevealState.AUTHORIZED,
    )
    assert event.attributes["actuals"] == [1, 2, 3]


def test_recursive_redaction_covers_secret_uri_bearer_and_query() -> None:
    redacted = redact_mapping(
        {
            "password": "abc",
            "nested": {
                "url": "postgresql://user:pass@db/app?token=abc",
                "authorization": "Bearer abc.def",
            },
        }
    )
    assert redacted["password"] == REDACTED
    nested = redacted["nested"]
    assert isinstance(nested, dict)
    assert "user:pass" not in str(nested)
    assert "abc.def" not in str(nested)
    assert "token=abc" not in str(nested)


def test_protected_actuals_are_redacted_before_reveal_and_allowed_after_authorization() -> None:
    protected = redact_mapping({"actuals": [1, 2, 3]})
    authorized = redact_mapping({"actuals": [1, 2, 3]}, reveal_state=RevealState.AUTHORIZED)
    assert protected["actuals"] == PROTECTED_ACTUAL
    assert authorized["actuals"] == [1, 2, 3]


def test_factory_merges_nested_context_and_restores_it() -> None:
    assert current_telemetry_context().run_id is None
    with bind_telemetry_context(run_id="run-1", request_id="req-1"):
        with bind_telemetry_context(trace_id="a" * 32, span_id="b" * 16):
            event = build_event(
                "model.predict.completed",
                component=Component.FORECAST_WORKER,
                status=EventStatus.PASS,
                stage=Stage.PREDICT,
            )
            assert event.run_id == "run-1"
            assert event.request_id == "req-1"
            assert event.trace_id == "a" * 32
            assert event.span_id == "b" * 16
        assert current_telemetry_context().trace_id is None
    assert current_telemetry_context().run_id is None


def test_factory_does_not_store_exception_message() -> None:
    event = build_event(
        "model.predict.failed",
        component=Component.FORECAST_WORKER,
        status=EventStatus.FAILED,
        exception=RuntimeError("password=super-secret"),
    )
    encoded = encode_event_json(event).decode("utf-8")
    assert event.error_code is ErrorCode.UNKNOWN_ERROR
    assert event.attributes["exception_type"] == "RuntimeError"
    assert "super-secret" not in encoded


def test_canonical_json_and_hash_are_deterministic() -> None:
    left = _event(attributes={"b": 2, "a": 1})
    right = _event(attributes={"a": 1, "b": 2})
    assert encode_event_json(left) == encode_event_json(right)
    assert event_sha256(left) == event_sha256(right)
    assert json.loads(encode_event_json(left))["schema_version"] == "1.0.0"


def test_metric_definition_rejects_prohibited_and_unbounded_labels() -> None:
    with pytest.raises(ValidationError):
        MetricDefinition(
            name="loto_bad_total",
            kind=MetricKind.COUNTER,
            description="bad",
            unit="events",
            label_allowlist={"run_id": ("one",)},
        )
    with pytest.raises(ValidationError):
        MetricDefinition(
            name="loto_too_many_total",
            kind=MetricKind.COUNTER,
            description="bad",
            unit="events",
            label_allowlist={f"label_{i}": ("x",) for i in range(6)},
        )


def test_histogram_requires_reviewed_increasing_buckets() -> None:
    with pytest.raises(ValidationError):
        MetricDefinition(
            name="loto_latency_seconds",
            kind=MetricKind.HISTOGRAM,
            description="latency",
            unit="seconds",
        )
    definition = MetricDefinition(
        name="loto_latency_seconds",
        kind=MetricKind.HISTOGRAM,
        description="latency",
        unit="seconds",
        buckets=(0.01, 0.1, 1.0),
    )
    assert definition.buckets[-1] == 1.0


def test_metric_registry_rejects_duplicates_and_label_drift() -> None:
    registry = MetricRegistry()
    definition = MetricDefinition(
        name="loto_test_total",
        kind=MetricKind.COUNTER,
        description="test",
        unit="events",
        label_allowlist={"status": ("PASS", "FAILED")},
    )
    registry.register(definition)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(definition)
    registry.validate_labels("loto_test_total", {"status": "PASS"})
    with pytest.raises(ValueError):
        registry.validate_labels("loto_test_total", {"status": "UNKNOWN"})
    with pytest.raises(ValueError):
        registry.validate_labels("loto_test_total", {})


def test_default_registry_has_only_bounded_self_observation_metrics() -> None:
    registry = default_telemetry_metric_registry()
    names = {item.name for item in registry.definitions()}
    assert names == {
        "loto_telemetry_buffer_size",
        "loto_telemetry_dropped_total",
        "loto_telemetry_events_total",
    }
    registry.validate_labels(
        "loto_telemetry_events_total",
        {"component": "evaluation", "status": "PASS"},
    )


def test_bounded_buffer_drops_optional_and_blocks_required_without_waiting() -> None:
    first = _event(event_name="model.predict.started", status=EventStatus.STARTED)
    second = _event()
    buffer = BoundedTelemetryBuffer(max_events=1)
    assert buffer.emit(first).status is EmitStatus.ACCEPTED
    optional = buffer.emit(second, importance=EventImportance.OPTIONAL_OPERATIONAL)
    required = buffer.emit(second, importance=EventImportance.REQUIRED_AUDIT)
    assert optional.status is EmitStatus.DROPPED
    assert required.status is EmitStatus.BLOCKED
    assert optional.error_code is ErrorCode.BUFFER_FULL
    assert required.error_code is ErrorCode.BUFFER_FULL
    assert buffer.snapshot() == (first,)
    assert buffer.dropped_count == 1
    assert buffer.blocked_count == 1


def test_buffer_drain_is_bounded_and_preserves_order() -> None:
    events = [_event(event_name=f"model.predict.step_{index}") for index in range(3)]
    buffer = BoundedTelemetryBuffer(max_events=3)
    for event in events:
        buffer.emit(event)
    assert buffer.drain(limit=2) == tuple(events[:2])
    assert buffer.snapshot() == (events[2],)


def test_redaction_property_never_retains_generated_secret_values() -> None:
    for index in range(100):
        secret = f"secret-{index}-value"
        payload = {
            "token": secret,
            "nested": {"database_url": f"postgresql://user:{secret}@db/app"},
            "safe": index,
        }
        encoded = json.dumps(redact_mapping(payload), sort_keys=True)
        assert secret not in encoded


def test_finite_property_accepts_representative_safe_numbers() -> None:
    values = [0, 1, -1, 1e-12, 1e12, math.pi]
    for value in values:
        assert _event(attributes={"value": value}).attributes["value"] == value

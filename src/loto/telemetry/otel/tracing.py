"""Local OpenTelemetry provider construction and safe domain spans."""
from __future__ import annotations

import math
import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer

from loto.telemetry.context import bind_telemetry_context, current_telemetry_context
from loto.telemetry.contracts import EventStatus, Stage
from loto.telemetry.otel.config import OtlpProtocol, TracingConfig, TracingRuntimeStatus
from loto.telemetry.otel.exporters import ExporterSnapshot, TrackingSpanExporter
from loto.telemetry.otel.processor import BoundedBatchSpanProcessor, ProcessorSnapshot
from loto.telemetry.redaction import (
    is_protected_actual_key,
    is_sensitive_key,
    redact_string,
)

_ATTRIBUTE_KEY_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
MAX_SPAN_ATTRIBUTES = 32
MAX_SPAN_STRING = 256

SPAN_NAME_BY_STAGE: dict[Stage, str] = {
    Stage.RECEIVE: "loto.api.request",
    Stage.DATA_LOAD: "loto.data.load",
    Stage.DATA_VALIDATE: "loto.data.validate",
    Stage.SPLIT_CREATE: "loto.split.create",
    Stage.FEATURE_FIT: "loto.feature.fit",
    Stage.FEATURE_TRANSFORM: "loto.feature.transform",
    Stage.HPO_STUDY: "loto.hpo.study",
    Stage.HPO_TRIAL: "loto.hpo.trial",
    Stage.MODEL_LOAD: "loto.model.load",
    Stage.FIT: "loto.model.fit",
    Stage.PREDICT: "loto.model.predict",
    Stage.PREDICTION_LOCK: "loto.prediction.lock",
    Stage.ACTUAL_READ: "loto.actual.read",
    Stage.SCORE: "loto.evaluation.score",
    Stage.ARTIFACT_PERSIST: "loto.artifact.persist",
    Stage.REGISTRY_PERSIST: "loto.registry.persist",
    Stage.PROMOTION_EVALUATE: "loto.promotion.evaluate",
    Stage.HEALTH: "loto.health.probe",
    Stage.TELEMETRY: "loto.telemetry.export",
}


def _safe_attribute_value(
    value: Any,
) -> str | bool | int | float | Sequence[str | bool | int | float] | None:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return redact_string(value)[:MAX_SPAN_STRING]
    if isinstance(value, (list, tuple)):
        safe: list[str | bool | int | float] = []
        for item in value[:32]:
            if isinstance(item, (bool, int)):
                safe.append(item)
            elif isinstance(item, float):
                if not math.isfinite(item):
                    return None
                safe.append(item)
            elif isinstance(item, str):
                safe.append(redact_string(item)[:MAX_SPAN_STRING])
            else:
                return None
        return tuple(safe)
    return None


def sanitize_span_attributes(values: Mapping[str, Any] | None) -> dict[str, Any]:
    """Drop protected/sensitive keys and retain only bounded OTel scalar values."""

    output: dict[str, Any] = {}
    for key, value in (values or {}).items():
        key = str(key)
        if len(output) >= MAX_SPAN_ATTRIBUTES:
            break
        if not _ATTRIBUTE_KEY_RE.fullmatch(key):
            continue
        if is_sensitive_key(key) or is_protected_actual_key(key):
            continue
        safe = _safe_attribute_value(value)
        if safe is not None:
            output[key] = safe
    return output


@dataclass(frozen=True, slots=True)
class TracingRuntime:
    config: TracingConfig
    status: TracingRuntimeStatus
    tracer: Tracer
    provider: TracerProvider | None = None
    exporter: TrackingSpanExporter | None = None
    processor: BoundedBatchSpanProcessor | None = None
    reason: str | None = None

    @property
    def is_active(self) -> bool:
        return self.provider is not None and self.status in {
            TracingRuntimeStatus.NOT_PROBED,
            TracingRuntimeStatus.DEGRADED,
            TracingRuntimeStatus.VERIFIED,
        }

    def force_flush(self) -> TracingRuntime:
        if self.processor is None or self.exporter is None:
            return self
        timeout_ms = int(self.config.export_timeout_seconds * 1000)
        flushed = self.processor.force_flush(timeout_millis=timeout_ms)
        processor = self.processor.snapshot()
        exporter = self.exporter.snapshot()
        if not flushed or processor.dropped or processor.export_failures or exporter.failed:
            return replace(self, status=TracingRuntimeStatus.DEGRADED, reason="export_degraded")
        if exporter.succeeded:
            return replace(
                self,
                status=TracingRuntimeStatus.NOT_PROBED,
                reason="export_accepted_unverified",
            )
        return replace(self, status=TracingRuntimeStatus.NOT_PROBED, reason="no_spans_exported")

    def exporter_snapshot(self) -> ExporterSnapshot | None:
        return None if self.exporter is None else self.exporter.snapshot()

    def processor_snapshot(self) -> ProcessorSnapshot | None:
        return None if self.processor is None else self.processor.snapshot()

    def shutdown(self) -> None:
        if self.provider is not None:
            self.provider.shutdown()


def _build_otlp_exporter(config: TracingConfig) -> SpanExporter:
    assert config.otlp_endpoint is not None
    if config.otlp_protocol is OtlpProtocol.GRPC:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter(
            endpoint=config.otlp_endpoint,
            timeout=config.export_timeout_seconds,
            insecure=config.otlp_endpoint.startswith("http://"),
        )
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    endpoint = config.otlp_endpoint
    if not endpoint.endswith("/v1/traces"):
        endpoint = f"{endpoint}/v1/traces"
    return OTLPSpanExporter(endpoint=endpoint, timeout=config.export_timeout_seconds)


def configure_tracing(
    config: TracingConfig,
    *,
    exporter: SpanExporter | None = None,
) -> TracingRuntime:
    """Construct an isolated provider; global installation and app wiring are explicit."""

    noop = trace.NoOpTracerProvider().get_tracer(config.service_name, config.service_version)
    if not config.enabled:
        return TracingRuntime(config, TracingRuntimeStatus.NOT_CONFIGURED, noop, reason="disabled")
    if config.service_version == "UNPINNED":
        return TracingRuntime(
            config,
            TracingRuntimeStatus.BLOCKED,
            noop,
            reason="service_version_unpinned",
        )
    if exporter is None and config.otlp_endpoint is None:
        return TracingRuntime(
            config,
            TracingRuntimeStatus.BLOCKED,
            noop,
            reason="otlp_endpoint_missing",
        )
    try:
        delegate = exporter or _build_otlp_exporter(config)
        tracked = TrackingSpanExporter(delegate)
        resource_values: dict[str, Any] = {
            "service.name": config.service_name,
            "service.version": config.service_version,
            "deployment.environment.name": config.environment,
            **config.resource_attributes,
        }
        provider = TracerProvider(
            resource=Resource.create(resource_values),
            sampler=ParentBased(TraceIdRatioBased(config.sample_ratio)),
        )
        processor = BoundedBatchSpanProcessor(
            tracked,
            max_queue_size=config.batch_queue_size,
            max_export_batch_size=config.batch_size,
            schedule_delay_seconds=min(0.1, config.export_timeout_seconds / 2.0),
            shutdown_timeout_seconds=config.export_timeout_seconds,
        )
        provider.add_span_processor(processor)
        tracer = provider.get_tracer(config.service_name, config.service_version)
        return TracingRuntime(
            config,
            TracingRuntimeStatus.NOT_PROBED,
            tracer,
            provider=provider,
            exporter=tracked,
            processor=processor,
        )
    except BaseException as exc:
        return TracingRuntime(
            config,
            TracingRuntimeStatus.BLOCKED,
            noop,
            reason=f"configuration_error:{type(exc).__name__}",
        )


@contextmanager
def domain_span(
    runtime: TracingRuntime,
    stage: Stage,
    *,
    platform_status: EventStatus = EventStatus.PASS,
    attributes: Mapping[str, Any] | None = None,
) -> Iterator[trace.Span]:
    """Start a required domain span and correlate it with the telemetry context."""

    base_attributes = sanitize_span_attributes(attributes)
    context = current_telemetry_context()
    for key, value in context.as_dict().items():
        if key not in {"trace_id", "span_id"}:
            base_attributes[f"loto.{key}"] = value
    base_attributes["loto.stage"] = stage.value
    base_attributes["loto.status"] = platform_status.value
    with runtime.tracer.start_as_current_span(
        SPAN_NAME_BY_STAGE[stage],
        kind=SpanKind.INTERNAL,
        attributes=base_attributes,
    ) as span:
        span_context = span.get_span_context()
        correlation: dict[str, str] = {}
        if span_context.is_valid:
            correlation = {
                "trace_id": format(span_context.trace_id, "032x"),
                "span_id": format(span_context.span_id, "016x"),
            }
        with bind_telemetry_context(**correlation):
            try:
                yield span
            except BaseException as exc:
                span.set_attribute("error.type", type(exc).__name__[:MAX_SPAN_STRING])
                span.set_attribute("loto.status", EventStatus.FAILED.value)
                span.set_status(Status(StatusCode.ERROR))
                raise
            else:
                if platform_status in {EventStatus.BLOCKED, EventStatus.FAILED}:
                    span.set_status(Status(StatusCode.ERROR))
                else:
                    span.set_status(Status(StatusCode.OK))

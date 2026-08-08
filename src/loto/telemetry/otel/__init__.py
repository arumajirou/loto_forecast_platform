"""Optional OpenTelemetry integration. Requires the repository ``full`` extra."""

from .asgi import OpenTelemetryASGIMiddleware, instrument_fastapi_app
from .config import OtlpProtocol, TracingConfig, TracingRuntimeStatus
from .exporters import ExporterSnapshot, TrackingSpanExporter
from .httpx_instrumentation import TracedAsyncHTTPTransport, TracedHTTPTransport
from .processor import BoundedBatchSpanProcessor, ProcessorSnapshot
from .sqlalchemy_instrumentation import instrument_sqlalchemy_engine, uninstrument_sqlalchemy_engine
from .tracing import (
    FORECAST_RUN_SPAN_NAME,
    SPAN_NAME_BY_STAGE,
    TracingRuntime,
    configure_tracing,
    domain_span,
    forecast_run_span,
    sanitize_span_attributes,
)

__all__ = [
    "BoundedBatchSpanProcessor",
    "ExporterSnapshot",
    "FORECAST_RUN_SPAN_NAME",
    "OpenTelemetryASGIMiddleware",
    "ProcessorSnapshot",
    "OtlpProtocol",
    "SPAN_NAME_BY_STAGE",
    "TracedAsyncHTTPTransport",
    "TracedHTTPTransport",
    "TracingConfig",
    "TracingRuntime",
    "TracingRuntimeStatus",
    "TrackingSpanExporter",
    "configure_tracing",
    "domain_span",
    "forecast_run_span",
    "instrument_fastapi_app",
    "instrument_sqlalchemy_engine",
    "sanitize_span_attributes",
    "uninstrument_sqlalchemy_engine",
]

from __future__ import annotations

import asyncio
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import ValidationError
from sqlalchemy import create_engine, text

from loto.telemetry import EventStatus, Stage, bind_telemetry_context, current_telemetry_context
from loto.telemetry.otel import (
    OtlpProtocol,
    TracedAsyncHTTPTransport,
    TracedHTTPTransport,
    TracingConfig,
    TracingRuntimeStatus,
    configure_tracing,
    domain_span,
    forecast_run_span,
    instrument_fastapi_app,
    instrument_sqlalchemy_engine,
    sanitize_span_attributes,
    uninstrument_sqlalchemy_engine,
)


def _runtime(**updates):
    exporter = InMemorySpanExporter()
    config = TracingConfig(enabled=True, service_version="test", **updates)
    runtime = configure_tracing(config, exporter=exporter)
    assert runtime.status is TracingRuntimeStatus.NOT_PROBED
    return runtime, exporter


def test_disabled_is_not_configured_and_enabled_without_exporter_is_blocked() -> None:
    disabled = configure_tracing(TracingConfig())
    assert disabled.status is TracingRuntimeStatus.NOT_CONFIGURED
    blocked = configure_tracing(TracingConfig(enabled=True, service_version="test"))
    assert blocked.status is TracingRuntimeStatus.BLOCKED
    assert blocked.reason == "otlp_endpoint_missing"


def test_configuration_is_strict_and_batch_is_bounded() -> None:
    with pytest.raises(ValidationError):
        TracingConfig(enabled=1)
    with pytest.raises(ValidationError):
        TracingConfig(batch_queue_size=64, batch_size=65)
    with pytest.raises(ValidationError):
        TracingConfig(otlp_endpoint="http://user:pass@collector:4318")
    with pytest.raises(ValidationError):
        TracingConfig(resource_attributes={"api_token": "secret"})


def test_domain_spans_cover_required_stages_and_share_trace() -> None:
    runtime, exporter = _runtime()
    with bind_telemetry_context(run_id="run-1", game_id="numbers4", seed=1):
        with forecast_run_span(runtime) as forecast:
            forecast_context = forecast.get_span_context()
            with domain_span(runtime, Stage.FIT, attributes={"safe.value": 1}) as parent:
                parent_context = parent.get_span_context()
                assert current_telemetry_context().trace_id == format(
                    parent_context.trace_id, "032x"
                )
                assert parent_context.trace_id == forecast_context.trace_id
                with domain_span(runtime, Stage.PREDICT) as child:
                    assert child.get_span_context().trace_id == parent_context.trace_id
    assert current_telemetry_context().run_id is None
    runtime = runtime.force_flush()
    assert runtime.status is TracingRuntimeStatus.NOT_PROBED
    assert runtime.reason == "export_accepted_unverified"
    spans = exporter.get_finished_spans()
    assert {span.name for span in spans} == {
        "loto.forecast.run",
        "loto.model.fit",
        "loto.model.predict",
    }
    child = next(span for span in spans if span.name == "loto.model.predict")
    assert child.parent is not None
    assert child.parent.span_id == parent_context.span_id
    runtime.shutdown()


def test_domain_exception_records_type_but_not_message() -> None:
    runtime, exporter = _runtime()
    with pytest.raises(RuntimeError, match="super-secret"):
        with domain_span(runtime, Stage.PREDICT):
            raise RuntimeError("password=super-secret")
    runtime = runtime.force_flush()
    span = exporter.get_finished_spans()[0]
    encoded = json.dumps(dict(span.attributes), sort_keys=True)
    assert span.attributes["error.type"] == "RuntimeError"
    assert "super-secret" not in encoded
    assert "password=" not in encoded
    runtime.shutdown()


def test_span_attribute_sanitizer_drops_secret_actual_nested_and_unsafe_values() -> None:
    result = sanitize_span_attributes(
        {
            "password": "abc",
            "actuals": [1, 2, 3],
            "safe.url": "http://user:pass@example.test/path?token=abc",
            "nested": {"value": 1},
            "safe.list": ["one", "two"],
            "nonfinite": float("nan"),
        }
    )
    assert "password" not in result
    assert "actuals" not in result
    assert "nested" not in result
    assert "user:pass" not in result["safe.url"]
    assert "token=abc" not in result["safe.url"]
    assert result["safe.list"] == ("one", "two")
    assert "nonfinite" not in result


def test_fastapi_middleware_correlates_existing_request_id_without_generating_one() -> None:
    runtime, exporter = _runtime()
    app = FastAPI()

    @app.get("/items/{item_id}")
    def item(item_id: str) -> dict[str, str | None]:
        context = current_telemetry_context()
        return {
            "request_id": context.request_id,
            "trace_id": context.trace_id,
            "span_id": context.span_id,
        }

    assert instrument_fastapi_app(app, runtime)
    assert not instrument_fastapi_app(app, runtime)
    with TestClient(app) as client:
        response = client.get("/items/secret-id?token=secret", headers={"x-request-id": "req-1"})
        assert response.status_code == 200
        body = response.json()
        assert body["request_id"] == "req-1"
        assert len(body["trace_id"]) == 32
        assert len(body["span_id"]) == 16
        response_without = client.get("/items/another")
        assert response_without.json()["request_id"] is None
    runtime = runtime.force_flush()
    spans = [span for span in exporter.get_finished_spans() if span.name == "loto.api.request"]
    assert len(spans) == 2
    serialized = json.dumps([dict(span.attributes) for span in spans], sort_keys=True)
    assert "secret-id" not in serialized
    assert "token=secret" not in serialized
    runtime.shutdown()


def test_httpx_transport_propagates_trace_without_recording_url_path_or_query() -> None:
    runtime, exporter = _runtime()
    observed: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["traceparent"] = request.headers.get("traceparent", "")
        return httpx.Response(204)

    transport = TracedHTTPTransport(runtime, httpx.MockTransport(handler))
    with httpx.Client(transport=transport) as client:
        with domain_span(runtime, Stage.PREDICT):
            response = client.get("https://example.test/private/42?token=secret")
    assert response.status_code == 204
    assert observed["traceparent"].startswith("00-")
    runtime = runtime.force_flush()
    spans = exporter.get_finished_spans()
    client_span = next(span for span in spans if span.name == "loto.http.client")
    attrs = json.dumps(dict(client_span.attributes), sort_keys=True)
    assert "private" not in attrs
    assert "token" not in attrs
    assert client_span.parent is not None
    runtime.shutdown()


def test_async_httpx_transport_exports_span() -> None:
    runtime, exporter = _runtime()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    async def execute() -> None:
        transport = TracedAsyncHTTPTransport(runtime, httpx.MockTransport(handler))
        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.get("https://example.test/resource")
            assert response.status_code == 200

    asyncio.run(execute())
    runtime = runtime.force_flush()
    assert any(span.name == "loto.http.client" for span in exporter.get_finished_spans())
    runtime.shutdown()


def test_sqlalchemy_instrumentation_records_operation_without_statement_or_parameters() -> None:
    runtime, exporter = _runtime()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    assert instrument_sqlalchemy_engine(engine, runtime)
    assert not instrument_sqlalchemy_engine(engine, runtime)
    with engine.begin() as connection:
        connection.execute(text("create table secrets (value text)"))
        connection.execute(text("insert into secrets(value) values (:value)"), {"value": "secret"})
        assert connection.execute(text("select value from secrets")).scalar_one() == "secret"
    assert uninstrument_sqlalchemy_engine(engine)
    assert not uninstrument_sqlalchemy_engine(engine)
    runtime = runtime.force_flush()
    spans = [span for span in exporter.get_finished_spans() if span.name == "loto.db.query"]
    assert len(spans) == 3
    attrs = json.dumps([dict(span.attributes) for span in spans], sort_keys=True).lower()
    assert "insert into" not in attrs
    assert "select value" not in attrs
    assert '"secret"' not in attrs
    operations = {span.attributes["db.operation.name"] for span in spans}
    assert operations == {"CREATE", "INSERT", "SELECT"}
    runtime.shutdown()


class FailingExporter(SpanExporter):
    def export(self, spans):
        return SpanExportResult.FAILURE

    def shutdown(self):
        return None


def test_export_failure_becomes_degraded_without_exception_message() -> None:
    config = TracingConfig(enabled=True, service_version="test")
    runtime = configure_tracing(config, exporter=FailingExporter())
    with domain_span(runtime, Stage.TELEMETRY):
        pass
    runtime = runtime.force_flush()
    assert runtime.status is TracingRuntimeStatus.DEGRADED
    snapshot = runtime.exporter_snapshot()
    assert snapshot is not None
    assert snapshot.failed == 1
    assert snapshot.last_error_type is None
    runtime.shutdown()


def test_console_exporter_smoke() -> None:
    output = io.StringIO()
    runtime = configure_tracing(
        TracingConfig(enabled=True, service_version="test"),
        exporter=ConsoleSpanExporter(out=output),
    )
    with domain_span(runtime, Stage.DATA_VALIDATE, platform_status=EventStatus.PASS):
        pass
    runtime = runtime.force_flush()
    assert runtime.status is TracingRuntimeStatus.NOT_PROBED
    assert runtime.reason == "export_accepted_unverified"
    assert "loto.data.validate" in output.getvalue()
    runtime.shutdown()


class _CaptureHandler(BaseHTTPRequestHandler):
    received: list[tuple[str, bytes, str]] = []

    def do_POST(self):
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length)
        type(self).received.append((self.path, body, self.headers.get("content-type", "")))
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return None


def test_otlp_http_loopback_stub_smoke() -> None:
    _CaptureHandler.received.clear()
    server = HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        runtime = configure_tracing(
            TracingConfig(
                enabled=True,
                service_version="test",
                otlp_endpoint=endpoint,
                otlp_protocol=OtlpProtocol.HTTP_PROTOBUF,
                export_timeout_seconds=2.0,
                batch_queue_size=64,
                batch_size=8,
            )
        )
        assert runtime.status is TracingRuntimeStatus.NOT_PROBED
        with domain_span(runtime, Stage.ARTIFACT_PERSIST):
            pass
        runtime = runtime.force_flush()
        assert runtime.status is TracingRuntimeStatus.NOT_PROBED
        assert runtime.reason == "export_accepted_unverified"
        assert _CaptureHandler.received
        path, body, content_type = _CaptureHandler.received[0]
        assert path == "/v1/traces"
        assert body
        assert "protobuf" in content_type
        runtime.shutdown()
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_enabled_runtime_rejects_unpinned_service_version() -> None:
    runtime = configure_tracing(TracingConfig(enabled=True), exporter=InMemorySpanExporter())
    assert runtime.status is TracingRuntimeStatus.BLOCKED
    assert runtime.reason == "service_version_unpinned"


class BlockingExporter(SpanExporter):
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def export(self, spans):
        self.started.set()
        self.release.wait(timeout=2)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        return None


def test_bounded_processor_drops_without_blocking_producer() -> None:
    exporter = BlockingExporter()
    runtime = configure_tracing(
        TracingConfig(
            enabled=True,
            service_version="test",
            export_timeout_seconds=0.05,
            batch_queue_size=64,
            batch_size=1,
        ),
        exporter=exporter,
    )
    with runtime.tracer.start_as_current_span("first"):
        pass
    assert exporter.started.wait(timeout=1)
    for index in range(200):
        with runtime.tracer.start_as_current_span(f"queued-{index}"):
            pass
    runtime = runtime.force_flush()
    snapshot = runtime.processor_snapshot()
    assert snapshot is not None
    assert snapshot.dropped > 0
    assert runtime.status is TracingRuntimeStatus.DEGRADED
    assert runtime.reason == "export_degraded"
    exporter.release.set()
    runtime.shutdown()


def test_platform_failed_status_marks_domain_span_error() -> None:
    runtime, exporter = _runtime()
    with domain_span(runtime, Stage.SCORE, platform_status=EventStatus.FAILED):
        pass
    runtime = runtime.force_flush()
    span = exporter.get_finished_spans()[0]
    assert span.status.status_code.name == "ERROR"
    runtime.shutdown()


def test_httpx_client_4xx_marks_span_error() -> None:
    runtime, exporter = _runtime()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    transport = TracedHTTPTransport(runtime, httpx.MockTransport(handler))
    with httpx.Client(transport=transport) as client:
        assert client.get("https://example.test/not-found").status_code == 404
    runtime = runtime.force_flush()
    span = next(span for span in exporter.get_finished_spans() if span.name == "loto.http.client")
    assert span.status.status_code.name == "ERROR"
    runtime.shutdown()

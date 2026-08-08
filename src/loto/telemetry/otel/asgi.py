"""FastAPI/ASGI request tracing without taking ownership of request-ID generation."""

from __future__ import annotations

import re
from typing import Any

from opentelemetry import propagate
from opentelemetry.trace import SpanKind, Status, StatusCode

from loto.telemetry.context import bind_telemetry_context
from loto.telemetry.otel.tracing import TracingRuntime

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _headers(scope: dict[str, Any]) -> dict[str, str]:
    return {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", ())
    }


class OpenTelemetryASGIMiddleware:
    """Trace HTTP requests while omitting raw paths, queries, bodies and headers."""

    def __init__(self, app: Any, *, runtime: TracingRuntime) -> None:
        self.app = app
        self.runtime = runtime

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope.get("type") != "http"
            or not self.runtime.config.instrument_fastapi
            or not self.runtime.is_active
        ):
            await self.app(scope, receive, send)
            return
        headers = _headers(scope)
        parent = propagate.extract(headers)
        attributes: dict[str, Any] = {
            "http.request.method": scope.get("method", "UNKNOWN"),
            "url.scheme": scope.get("scheme", "http"),
        }
        server = scope.get("server")
        if server:
            attributes["server.address"] = str(server[0])[:256]
            attributes["server.port"] = int(server[1])
        request_id = headers.get("x-request-id")
        if request_id is not None and not _REQUEST_ID_RE.fullmatch(request_id):
            request_id = None

        with self.runtime.tracer.start_as_current_span(
            "loto.api.request",
            context=parent,
            kind=SpanKind.SERVER,
            attributes=attributes,
        ) as span:
            span_context = span.get_span_context()
            correlation: dict[str, str] = {}
            if span_context.is_valid:
                correlation["trace_id"] = format(span_context.trace_id, "032x")
                correlation["span_id"] = format(span_context.span_id, "016x")
            if request_id is not None:
                correlation["request_id"] = request_id

            async def traced_send(message: dict[str, Any]) -> None:
                if message.get("type") == "http.response.start":
                    status_code = int(message.get("status", 500))
                    span.set_attribute("http.response.status_code", status_code)
                    if status_code >= 500:
                        span.set_status(Status(StatusCode.ERROR))
                await send(message)

            with bind_telemetry_context(**correlation):
                try:
                    await self.app(scope, receive, traced_send)
                except BaseException as exc:
                    span.set_attribute("error.type", type(exc).__name__[:256])
                    span.set_status(Status(StatusCode.ERROR))
                    raise


def instrument_fastapi_app(app: Any, runtime: TracingRuntime) -> bool:
    """Add the middleware once. Request-ID generation remains owned by PR #127."""

    if not runtime.config.instrument_fastapi or not runtime.is_active:
        return False
    marker = "_loto_otel_instrumented"
    if getattr(app.state, marker, False):
        return False
    app.add_middleware(OpenTelemetryASGIMiddleware, runtime=runtime)
    setattr(app.state, marker, True)
    return True

"""Explicit HTTPX transport wrappers with W3C propagation and bounded attributes."""
from __future__ import annotations

from typing import Any

import httpx
from opentelemetry import propagate
from opentelemetry.trace import SpanKind, Status, StatusCode

from loto.telemetry.otel.tracing import TracingRuntime


def _request_attributes(request: httpx.Request) -> dict[str, Any]:
    port = request.url.port
    attributes: dict[str, Any] = {
        "http.request.method": request.method,
        "server.address": request.url.host[:256],
        "url.scheme": request.url.scheme,
    }
    if port is not None:
        attributes["server.port"] = port
    return attributes


def _inject(request: httpx.Request) -> None:
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    for key, value in carrier.items():
        request.headers[key] = value


class TracedHTTPTransport(httpx.BaseTransport):
    def __init__(
        self, runtime: TracingRuntime, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.runtime = runtime
        self.transport = transport or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if not self.runtime.config.instrument_httpx or not self.runtime.is_active:
            return self.transport.handle_request(request)
        with self.runtime.tracer.start_as_current_span(
            "loto.http.client",
            kind=SpanKind.CLIENT,
            attributes=_request_attributes(request),
        ) as span:
            _inject(request)
            try:
                response = self.transport.handle_request(request)
            except BaseException as exc:
                span.set_attribute("error.type", type(exc).__name__[:256])
                span.set_status(Status(StatusCode.ERROR))
                raise
            span.set_attribute("http.response.status_code", response.status_code)
            if response.status_code >= 400:
                span.set_status(Status(StatusCode.ERROR))
            return response

    def close(self) -> None:
        self.transport.close()


class TracedAsyncHTTPTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        runtime: TracingRuntime,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.runtime = runtime
        self.transport = transport or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if not self.runtime.config.instrument_httpx or not self.runtime.is_active:
            return await self.transport.handle_async_request(request)
        with self.runtime.tracer.start_as_current_span(
            "loto.http.client",
            kind=SpanKind.CLIENT,
            attributes=_request_attributes(request),
        ) as span:
            _inject(request)
            try:
                response = await self.transport.handle_async_request(request)
            except BaseException as exc:
                span.set_attribute("error.type", type(exc).__name__[:256])
                span.set_status(Status(StatusCode.ERROR))
                raise
            span.set_attribute("http.response.status_code", response.status_code)
            if response.status_code >= 400:
                span.set_status(Status(StatusCode.ERROR))
            return response

    async def aclose(self) -> None:
        await self.transport.aclose()

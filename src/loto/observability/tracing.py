from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Iterator
from typing import Any


class TraceManager:
    def __init__(
        self, service_name: str = "loto-forecast-platform", otlp_endpoint: str | None = None
    ):
        self.service_name = service_name
        self.otlp_endpoint = otlp_endpoint
        self.tracer = None
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider

            provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
            if otlp_endpoint:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                provider.add_span_processor(
                    BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
                )
            trace.set_tracer_provider(provider)
            self.tracer = trace.get_tracer(service_name)
        except Exception:
            self.tracer = None

    @contextlib.contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None) -> Iterator[None]:
        if self.tracer is None:
            started = time.perf_counter()
            try:
                yield
            finally:
                logging.getLogger(__name__).debug(
                    "span %s %.6fs", name, time.perf_counter() - started
                )
            return
        with self.tracer.start_as_current_span(name, attributes=attributes or {}):
            yield

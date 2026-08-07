"""Export outcome tracking without retaining payload or exception messages."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult


@dataclass(frozen=True, slots=True)
class ExporterSnapshot:
    attempts: int
    succeeded: int
    failed: int
    last_result: SpanExportResult | None
    last_duration_ms: float | None
    last_error_type: str | None


class TrackingSpanExporter(SpanExporter):
    """Track bounded exporter health while delegating actual export behavior."""

    def __init__(self, delegate: SpanExporter) -> None:
        self.delegate = delegate
        self._lock = Lock()
        self._attempts = 0
        self._succeeded = 0
        self._failed = 0
        self._last_result: SpanExportResult | None = None
        self._last_duration_ms: float | None = None
        self._last_error_type: str | None = None

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        started = monotonic()
        error_type: str | None = None
        try:
            result = self.delegate.export(spans)
        except BaseException as exc:  # exporter boundary must not leak messages
            result = SpanExportResult.FAILURE
            error_type = type(exc).__name__
        duration_ms = (monotonic() - started) * 1000.0
        with self._lock:
            self._attempts += 1
            self._last_result = result
            self._last_duration_ms = duration_ms
            self._last_error_type = error_type
            if result is SpanExportResult.SUCCESS:
                self._succeeded += 1
            else:
                self._failed += 1
        return result

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        flush = getattr(self.delegate, "force_flush", None)
        if flush is None:
            return True
        try:
            return bool(flush(timeout_millis=timeout_millis))
        except TypeError:
            return bool(flush(timeout_millis))
        except BaseException:
            return False

    def shutdown(self) -> None:
        try:
            self.delegate.shutdown()
        except BaseException:
            return None

    def snapshot(self) -> ExporterSnapshot:
        with self._lock:
            return ExporterSnapshot(
                attempts=self._attempts,
                succeeded=self._succeeded,
                failed=self._failed,
                last_result=self._last_result,
                last_duration_ms=self._last_duration_ms,
                last_error_type=self._last_error_type,
            )

"""Non-blocking bounded span processor with explicit queue-drop evidence."""

from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Condition, Event, Thread
from time import monotonic

from opentelemetry.context import Context
from opentelemetry.sdk.trace import ReadableSpan, Span
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult, SpanProcessor


@dataclass(frozen=True, slots=True)
class ProcessorSnapshot:
    accepted: int
    dropped: int
    exported_spans: int
    exported_batches: int
    export_failures: int
    pending: int
    worker_alive: bool


class BoundedBatchSpanProcessor(SpanProcessor):
    """Queue sampled spans without blocking producers and export on a daemon worker."""

    def __init__(
        self,
        exporter: SpanExporter,
        *,
        max_queue_size: int,
        max_export_batch_size: int,
        schedule_delay_seconds: float = 0.2,
        shutdown_timeout_seconds: float = 5.0,
    ) -> None:
        if max_queue_size < 1:
            raise ValueError("max_queue_size must be >= 1")
        if not 1 <= max_export_batch_size <= max_queue_size:
            raise ValueError("max_export_batch_size must be within queue capacity")
        if schedule_delay_seconds <= 0.0:
            raise ValueError("schedule_delay_seconds must be > 0")
        if shutdown_timeout_seconds <= 0.0:
            raise ValueError("shutdown_timeout_seconds must be > 0")
        self.exporter = exporter
        self.max_export_batch_size = max_export_batch_size
        self.schedule_delay_seconds = schedule_delay_seconds
        self.shutdown_timeout_seconds = shutdown_timeout_seconds
        self._queue: Queue[ReadableSpan] = Queue(maxsize=max_queue_size)
        self._shutdown = Event()
        self._wake = Event()
        self._condition = Condition()
        self._accepted = 0
        self._dropped = 0
        self._exported_spans = 0
        self._exported_batches = 0
        self._export_failures = 0
        self._pending = 0
        self._worker = Thread(
            target=self._run,
            name="loto-otel-export",
            daemon=True,
        )
        self._worker.start()

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        return None

    def on_end(self, span: ReadableSpan) -> None:
        if not span.context or not span.context.trace_flags.sampled:
            return
        with self._condition:
            try:
                self._queue.put_nowait(span)
            except Full:
                self._dropped += 1
                return
            self._accepted += 1
            self._pending += 1
        self._wake.set()

    def _take_batch(self) -> list[ReadableSpan]:
        try:
            first = self._queue.get(timeout=self.schedule_delay_seconds)
        except Empty:
            return []
        batch = [first]
        deadline = monotonic() + self.schedule_delay_seconds
        while len(batch) < self.max_export_batch_size:
            remaining = deadline - monotonic()
            if remaining <= 0.0:
                break
            try:
                batch.append(self._queue.get(timeout=remaining))
            except Empty:
                break
        return batch

    def _run(self) -> None:
        while not self._shutdown.is_set() or self._pending_count() > 0:
            batch = self._take_batch()
            if not batch:
                self._wake.wait(self.schedule_delay_seconds)
                self._wake.clear()
                continue
            result = self.exporter.export(batch)
            with self._condition:
                self._exported_batches += 1
                if result is SpanExportResult.SUCCESS:
                    self._exported_spans += len(batch)
                else:
                    self._export_failures += 1
                self._pending -= len(batch)
                self._condition.notify_all()
            for _ in batch:
                self._queue.task_done()

    def _pending_count(self) -> int:
        with self._condition:
            return self._pending

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        deadline = monotonic() + max(timeout_millis, 0) / 1000.0
        self._wake.set()
        with self._condition:
            while self._pending > 0:
                remaining = deadline - monotonic()
                if remaining <= 0.0:
                    return False
                self._condition.wait(timeout=remaining)
        return True

    def shutdown(self) -> None:
        self._shutdown.set()
        self._wake.set()
        timeout_ms = int(self.shutdown_timeout_seconds * 1000)
        self.force_flush(timeout_millis=timeout_ms)
        self._worker.join(timeout=self.shutdown_timeout_seconds)
        if not self._worker.is_alive():
            self.exporter.shutdown()

    def snapshot(self) -> ProcessorSnapshot:
        with self._condition:
            return ProcessorSnapshot(
                accepted=self._accepted,
                dropped=self._dropped,
                exported_spans=self._exported_spans,
                exported_batches=self._exported_batches,
                export_failures=self._export_failures,
                pending=self._pending,
                worker_alive=self._worker.is_alive(),
            )

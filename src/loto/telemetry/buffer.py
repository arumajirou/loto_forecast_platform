"""Non-blocking bounded local buffering with explicit drop/block outcomes."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum

from loto.telemetry.contracts import ErrorCode, TelemetryEvent


class EventImportance(StrEnum):
    REQUIRED_AUDIT = "REQUIRED_AUDIT"
    OPTIONAL_OPERATIONAL = "OPTIONAL_OPERATIONAL"


class EmitStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    DROPPED = "DROPPED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class EmitResult:
    status: EmitStatus
    error_code: ErrorCode | None
    buffer_size: int


class BoundedTelemetryBuffer:
    """A non-waiting buffer; required evidence fails closed when capacity is exhausted."""

    def __init__(self, max_events: int = 1024) -> None:
        if max_events < 1:
            raise ValueError("max_events must be >= 1")
        self._events: deque[TelemetryEvent] = deque()
        self.max_events = max_events
        self.dropped_count = 0
        self.blocked_count = 0

    def emit(
        self,
        event: TelemetryEvent,
        *,
        importance: EventImportance = EventImportance.OPTIONAL_OPERATIONAL,
    ) -> EmitResult:
        if len(self._events) < self.max_events:
            self._events.append(event)
            return EmitResult(EmitStatus.ACCEPTED, None, len(self._events))
        if importance is EventImportance.REQUIRED_AUDIT:
            self.blocked_count += 1
            return EmitResult(EmitStatus.BLOCKED, ErrorCode.BUFFER_FULL, len(self._events))
        self.dropped_count += 1
        return EmitResult(EmitStatus.DROPPED, ErrorCode.BUFFER_FULL, len(self._events))

    def drain(self, limit: int | None = None) -> tuple[TelemetryEvent, ...]:
        if limit is not None and limit < 1:
            raise ValueError("limit must be >= 1")
        count = len(self._events) if limit is None else min(limit, len(self._events))
        return tuple(self._events.popleft() for _ in range(count))

    def snapshot(self) -> tuple[TelemetryEvent, ...]:
        return tuple(self._events)

    def __len__(self) -> int:
        return len(self._events)

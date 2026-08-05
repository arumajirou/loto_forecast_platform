from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StatusEvent:
    recorded_at: datetime
    status: str
    evidence: str
    supersedes: tuple[str, ...] = ()


def current_status(events: Iterable[StatusEvent]) -> StatusEvent:
    ordered = sorted(events, key=lambda event: event.recorded_at)
    if not ordered:
        raise ValueError("at least one status event is required")
    seen: set[str] = set()
    for event in ordered:
        if event.evidence in seen:
            raise ValueError(f"duplicate status evidence: {event.evidence}")
        unknown = set(event.supersedes) - seen
        if unknown:
            raise ValueError(f"status event supersedes unknown evidence: {sorted(unknown)}")
        seen.add(event.evidence)
    return ordered[-1]


def canonical_status_events() -> tuple[StatusEvent, ...]:
    return (
        StatusEvent(
            recorded_at=datetime.fromisoformat("2026-08-01T11:44:00+00:00"),
            status="BLOCKED",
            evidence="blocked-reason.json",
        ),
        StatusEvent(
            recorded_at=datetime.fromisoformat("2026-08-01T12:29:10.660732+00:00"),
            status="CERTIFIED",
            evidence="runtime-certification.json",
            supersedes=("blocked-reason.json",),
        ),
    )

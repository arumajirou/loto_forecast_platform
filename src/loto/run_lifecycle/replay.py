"""Deterministic aggregate reconstruction from immutable events."""

from __future__ import annotations

from .events import verify_event_chain
from .models import HashBinding, RunAggregate, RunEvent, RunPhase, RunStatus


def replay_events(events: tuple[RunEvent, ...] | list[RunEvent]) -> RunAggregate:
    ordered = verify_event_chain(events)
    if not ordered:
        raise ValueError("replay requires at least one event")
    outputs: dict[str, str] = {}
    cancelled_at = None
    completed_at = None
    for event in ordered:
        for output in event.sealed_outputs:
            outputs.setdefault(output.name, output.sha256)
        if event.status == RunStatus.CANCELLED:
            cancelled_at = event.occurred_at
        if event.phase == RunPhase.COMPLETE and event.status == RunStatus.SUCCEEDED:
            completed_at = event.occurred_at
    last = ordered[-1]
    return RunAggregate(
        run_id=last.run_id,
        phase=last.phase,
        status=last.status,
        revision=last.revision,
        last_event_sha256=last.event_sha256,
        immutable_output_hashes=tuple(
            HashBinding(name=name, sha256=sha256) for name, sha256 in sorted(outputs.items())
        ),
        cancelled_at=cancelled_at,
        completed_at=completed_at,
    )

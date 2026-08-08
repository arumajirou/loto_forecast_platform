"""Append-only event creation, hashing, and integrity verification."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from .canonical import sha256_canonical
from .exceptions import EventChainError, LifecycleValidationError
from .models import (
    CanonicalJsonObject,
    EvidenceReference,
    HashBinding,
    RunAggregate,
    RunCommand,
    RunEvent,
    RunPhase,
    RunStatus,
    TransitionDecision,
)
from .transitions import TRANSITION_MATRIX


def event_hash_payload(event: RunEvent) -> dict[str, object]:
    """Return all event fields except the self-hash field."""

    return event.model_dump(mode="python", exclude={"event_sha256"})


def calculate_event_sha256(event: RunEvent) -> str:
    return sha256_canonical(event_hash_payload(event))


def build_event(
    *,
    aggregate: RunAggregate,
    command: RunCommand,
    decision: TransitionDecision,
    idempotency_key: str,
    occurred_at: datetime,
    payload: CanonicalJsonObject,
    sealed_outputs: tuple[HashBinding, ...],
    evidence_references: tuple[EvidenceReference, ...],
) -> RunEvent:
    if not decision.allowed or decision.target_phase is None or decision.target_status is None:
        raise LifecycleValidationError("cannot build event from rejected transition")
    provisional = RunEvent(
        run_id=aggregate.run_id,
        sequence=aggregate.revision + 1,
        revision=aggregate.revision + 1,
        expected_revision=aggregate.revision,
        command_id=command.command_id,
        command_type=command.command_type,
        idempotency_key=idempotency_key,
        phase=decision.target_phase,
        status=decision.target_status,
        occurred_at=occurred_at,
        previous_event_sha256=aggregate.last_event_sha256,
        payload=payload,
        sealed_outputs=sealed_outputs,
        evidence_references=evidence_references,
        event_sha256="0" * 64,
    )
    return provisional.model_copy(update={"event_sha256": calculate_event_sha256(provisional)})


def verify_event_chain(events: Iterable[RunEvent]) -> tuple[RunEvent, ...]:
    """Validate complete ordered event history and return an immutable tuple."""

    ordered = tuple(events)
    if not ordered:
        return ordered
    run_id = ordered[0].run_id
    prior_phase = RunPhase.PLAN
    prior_status = RunStatus.PENDING
    prior_hash: str | None = None
    prior_time: datetime | None = None
    sealed_outputs: dict[str, str] = {}
    for expected_sequence, event in enumerate(ordered, start=1):
        if event.sequence != expected_sequence or event.revision != expected_sequence:
            raise EventChainError("event sequence must be ordered, unique, one-based and gap-free")
        if event.expected_revision != expected_sequence - 1:
            raise EventChainError("event expected_revision is inconsistent")
        if event.run_id != run_id:
            raise EventChainError("run_id changed inside the event chain")
        if event.previous_event_sha256 != prior_hash:
            raise EventChainError("previous_event_sha256 chain mismatch")
        if calculate_event_sha256(event) != event.event_sha256:
            raise EventChainError("event payload or metadata hash mismatch")
        if prior_time is not None and event.occurred_at < prior_time:
            raise EventChainError("event timestamps moved backwards")
        rule = TRANSITION_MATRIX.get((prior_phase, prior_status, event.command_type))
        if rule is None:
            raise EventChainError("event encodes an unknown transition")
        if event.phase != rule.to_phase or event.status != rule.to_status:
            raise EventChainError("event phase/status does not match transition matrix")
        for output in event.sealed_outputs:
            previous = sealed_outputs.get(output.name)
            if previous is not None and previous != output.sha256:
                raise EventChainError("immutable sealed output hash changed")
            sealed_outputs[output.name] = output.sha256
        prior_phase = event.phase
        prior_status = event.status
        prior_hash = event.event_sha256
        prior_time = event.occurred_at
    return ordered

from __future__ import annotations

from datetime import timedelta

import pytest

from loto.run_lifecycle import (
    EffectResult,
    EventChainError,
    HashBinding,
    RunCommandType,
    RunPhase,
    calculate_event_sha256,
    replay_events,
    validate_lifecycle,
    verify_event_chain,
)

from conftest import make_command


def _three_events(service, repository, clock):
    service.execute(make_command(command_id="start"))
    clock.advance(timedelta(seconds=1))
    service.execute(
        make_command(
            command_id="done-plan",
            command_type=RunCommandType.MARK_SUCCEEDED,
            phase=RunPhase.PLAN,
            expected_revision=1,
        ),
        lambda _: EffectResult(
            sealed_outputs=(HashBinding(name="plan-output", sha256="1" * 64),)
        ),
    )
    clock.advance(timedelta(seconds=1))
    service.execute(
        make_command(
            command_id="start-data",
            command_type=RunCommandType.START,
            phase=RunPhase.DATA,
            expected_revision=2,
        )
    )
    return repository.list_events("run-001")


def test_event_chain_and_replay_preserve_sealed_outputs(service, repository, clock) -> None:
    events = _three_events(service, repository, clock)
    assert verify_event_chain(events) == events
    aggregate = replay_events(events)
    assert aggregate.revision == 3
    assert aggregate.phase == RunPhase.DATA
    assert aggregate.immutable_output_hashes == (
        HashBinding(name="plan-output", sha256="1" * 64),
    )
    report = validate_lifecycle(events)
    assert report.valid
    assert report.validated_event_count == 3


@pytest.mark.parametrize("mutation", ["reorder", "delete", "insert", "payload"])
def test_chain_detects_reorder_deletion_insertion_and_tamper(
    service,
    repository,
    clock,
    mutation: str,
) -> None:
    events = list(_three_events(service, repository, clock))
    if mutation == "reorder":
        candidate = [events[1], events[0], events[2]]
    elif mutation == "delete":
        candidate = [events[0], events[2]]
    elif mutation == "insert":
        candidate = [events[0], events[1], events[1], events[2]]
    else:
        tampered = events[1].model_copy(
            update={"payload": events[1].payload.from_object({"tampered": True})}
        )
        candidate = [events[0], tampered, events[2]]
    with pytest.raises(EventChainError):
        verify_event_chain(candidate)


def test_phase_tamper_detected_even_after_rehash(service, repository, clock) -> None:
    events = list(_three_events(service, repository, clock))
    changed = events[1].model_copy(update={"phase": RunPhase.TRAIN})
    changed = changed.model_copy(update={"event_sha256": calculate_event_sha256(changed)})
    events[1] = changed
    events[2] = events[2].model_copy(
        update={"previous_event_sha256": changed.event_sha256}
    )
    events[2] = events[2].model_copy(
        update={"event_sha256": calculate_event_sha256(events[2])}
    )
    with pytest.raises(EventChainError, match="phase/status"):
        verify_event_chain(events)

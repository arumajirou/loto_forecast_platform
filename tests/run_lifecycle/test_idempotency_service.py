from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import make_command

from loto.run_lifecycle import (
    CanonicalJsonObject,
    EffectResult,
    HashBinding,
    IdempotencyConflictError,
    RunCommandType,
    RunStatus,
    TransitionRejected,
    compute_semantic_idempotency_key,
)


def test_semantic_key_excludes_timestamp_command_id_and_lease_fields() -> None:
    first = make_command(command_id="cmd-a")
    second = make_command(
        command_id="cmd-b",
        issued_at=first.issued_at + timedelta(hours=1),
        lease_id="lease-2",
        lease_owner_id="worker-2",
        fencing_token=99,
    )
    assert compute_semantic_idempotency_key(first) == compute_semantic_idempotency_key(second)


def test_duplicate_command_returns_verified_result_without_reexecuting_handler(
    service,
    repository,
    clock,
) -> None:
    calls = 0

    def effect(_):
        nonlocal calls
        calls += 1
        return EffectResult(payload=CanonicalJsonObject.from_object({"value": 7}))

    first = service.execute(make_command(command_id="cmd-a"), effect)
    clock.advance(timedelta(seconds=5))
    duplicate = service.execute(make_command(command_id="cmd-b"), effect)
    assert calls == 1
    assert not first.duplicate
    assert duplicate.duplicate
    assert not duplicate.effect_executed
    assert len(repository.list_events("run-001")) == 1
    record = repository.get_idempotency(first.idempotency_key)
    assert record is not None
    assert record.duplicate_count == 1
    assert record.duplicate_observations[0].command_id == "cmd-b"


def test_declared_key_with_different_payload_fails_closed(service) -> None:
    key = "a" * 64
    service.execute(
        make_command(
            command_id="cmd-a",
            declared_idempotency_key=key,
            semantic={"value": 1},
        )
    )
    with pytest.raises(IdempotencyConflictError):
        service.execute(
            make_command(
                command_id="cmd-b",
                declared_idempotency_key=key,
                semantic={"value": 2},
            )
        )


def test_duplicate_cancellation_is_idempotent(service, repository, clock) -> None:
    service.execute(make_command(command_id="start"))
    clock.advance(timedelta(seconds=1))
    cancel = make_command(
        command_id="cancel-a",
        command_type=RunCommandType.CANCEL,
        expected_revision=1,
    )
    first = service.execute(cancel)
    clock.advance(timedelta(seconds=1))
    duplicate = service.execute(
        cancel.model_copy(update={"command_id": "cancel-b", "issued_at": clock.now()})
    )
    assert first.aggregate.status == RunStatus.CANCELLED
    assert duplicate.duplicate
    assert len(repository.list_events("run-001")) == 2
    with pytest.raises(TransitionRejected, match="terminal-state-immutable"):
        service.execute(
            make_command(
                command_id="resume",
                command_type=RunCommandType.RESUME,
                expected_revision=2,
            )
        )


def test_resume_records_event_but_does_not_regenerate_sealed_output(
    service,
    repository,
    clock,
) -> None:
    service.execute(
        make_command(command_id="start"),
        lambda _: EffectResult(sealed_outputs=(HashBinding(name="checkpoint", sha256="b" * 64),)),
    )
    clock.advance(timedelta(seconds=1))
    service.execute(
        make_command(
            command_id="blocked",
            command_type=RunCommandType.MARK_BLOCKED,
            expected_revision=1,
        )
    )
    calls = 0

    def should_not_run(_):
        nonlocal calls
        calls += 1
        return EffectResult(sealed_outputs=(HashBinding(name="checkpoint", sha256="c" * 64),))

    clock.advance(timedelta(seconds=1))
    resumed = service.execute(
        make_command(
            command_id="resume",
            command_type=RunCommandType.RESUME,
            expected_revision=2,
            requested_output_names=("checkpoint",),
        ),
        should_not_run,
    )
    assert calls == 0
    assert not resumed.effect_executed
    assert resumed.event is not None
    assert resumed.event.command_type == RunCommandType.RESUME
    assert resumed.aggregate.immutable_output_hashes == (
        HashBinding(name="checkpoint", sha256="b" * 64),
    )
    assert len(repository.list_events("run-001")) == 3

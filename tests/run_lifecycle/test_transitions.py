from __future__ import annotations

import pytest

from loto.run_lifecycle import (
    RunAggregate,
    RunCommandType,
    RunPhase,
    RunStatus,
    TransitionEngine,
    TransitionRejected,
)
from tests.run_lifecycle.conftest import make_command


def test_unknown_transition_fails_closed() -> None:
    aggregate = RunAggregate.initial("run-001")
    command = make_command(
        command_id="cmd-1",
        command_type=RunCommandType.MARK_SUCCEEDED,
    )
    decision = TransitionEngine().decide(aggregate, command)
    assert not decision.allowed
    assert decision.reason_code == "unknown-transition"


def test_expected_revision_enforces_optimistic_concurrency() -> None:
    aggregate = RunAggregate.initial("run-001")
    command = make_command(command_id="cmd-1", expected_revision=1)
    decision = TransitionEngine().decide(aggregate, command)
    assert not decision.allowed
    assert decision.reason_code == "revision-mismatch"


def test_persist_retryable_failure_is_representable() -> None:
    aggregate = RunAggregate(
        run_id="run-001",
        phase=RunPhase.PERSIST,
        status=RunStatus.RUNNING,
        revision=8,
        last_event_sha256="a" * 64,
    )
    command = make_command(
        command_id="cmd-9",
        command_type=RunCommandType.MARK_RETRYABLE_FAILURE,
        phase=RunPhase.PERSIST,
        expected_revision=8,
    )
    decision = TransitionEngine().decide(aggregate, command)
    assert decision.allowed
    assert decision.target_phase == RunPhase.PERSIST
    assert decision.target_status == RunStatus.RETRYABLE_FAILURE


def test_terminal_states_are_immutable() -> None:
    aggregate = RunAggregate(
        run_id="run-001",
        phase=RunPhase.TRAIN,
        status=RunStatus.CANCELLED,
        revision=3,
        last_event_sha256="a" * 64,
        cancelled_at=make_command(command_id="x").issued_at,
    )
    command = make_command(
        command_id="cmd-4",
        command_type=RunCommandType.RESUME,
        phase=RunPhase.TRAIN,
        expected_revision=3,
    )
    decision = TransitionEngine().decide(aggregate, command)
    assert not decision.allowed
    assert decision.reason_code == "terminal-state-immutable"


def test_complete_succeeded_rejects_every_change() -> None:
    aggregate = RunAggregate(
        run_id="run-001",
        phase=RunPhase.COMPLETE,
        status=RunStatus.SUCCEEDED,
        revision=20,
        last_event_sha256="a" * 64,
        completed_at=make_command(command_id="x").issued_at,
    )
    command = make_command(
        command_id="cmd-21",
        command_type=RunCommandType.CANCEL,
        phase=RunPhase.COMPLETE,
        expected_revision=20,
    )
    decision = TransitionEngine().decide(aggregate, command)
    assert not decision.allowed
    assert decision.reason_code == "terminal-state-immutable"


def test_service_raises_machine_reason_on_rejection(service) -> None:
    with pytest.raises(TransitionRejected, match="unknown-transition"):
        service.execute(
            make_command(
                command_id="bad",
                command_type=RunCommandType.MARK_SUCCEEDED,
            )
        )

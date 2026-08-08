from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import make_command

from loto.run_lifecycle import (
    RunCommandType,
    RunPhase,
    RunStatus,
    TransitionRejected,
    replay_events,
)


def test_complete_lifecycle_replays_and_becomes_immutable(service, repository, clock) -> None:
    revision = 0
    phases = [phase for phase in RunPhase if phase != RunPhase.COMPLETE]
    for phase in phases:
        service.execute(
            make_command(
                command_id=f"start-{phase.value.lower()}",
                command_type=RunCommandType.START,
                phase=phase,
                expected_revision=revision,
            )
        )
        revision += 1
        clock.advance(timedelta(milliseconds=1))
        completed = service.execute(
            make_command(
                command_id=f"done-{phase.value.lower()}",
                command_type=RunCommandType.MARK_SUCCEEDED,
                phase=phase,
                expected_revision=revision,
            )
        )
        revision += 1
        clock.advance(timedelta(milliseconds=1))
    assert completed.aggregate.phase == RunPhase.COMPLETE
    assert completed.aggregate.status == RunStatus.SUCCEEDED
    replayed = replay_events(repository.list_events("run-001"))
    assert replayed == completed.aggregate
    with pytest.raises(TransitionRejected, match="terminal-state-immutable"):
        service.execute(
            make_command(
                command_id="after-complete",
                command_type=RunCommandType.CANCEL,
                phase=RunPhase.COMPLETE,
                expected_revision=revision,
            )
        )

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from loto.run_lifecycle import (
    CanonicalJsonObject,
    InMemoryLifecycleRepository,
    LifecycleService,
    ManualClock,
    RunCommand,
    RunCommandType,
    RunPhase,
)


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock(datetime(2026, 8, 6, 8, 0, tzinfo=UTC))


@pytest.fixture
def repository() -> InMemoryLifecycleRepository:
    return InMemoryLifecycleRepository()


@pytest.fixture
def service(
    repository: InMemoryLifecycleRepository,
    clock: ManualClock,
) -> LifecycleService:
    return LifecycleService(repository, clock)


def make_command(
    *,
    command_id: str,
    run_id: str = "run-001",
    command_type: RunCommandType = RunCommandType.START,
    phase: RunPhase = RunPhase.PLAN,
    expected_revision: int = 0,
    issued_at: datetime | None = None,
    semantic: dict[str, object] | None = None,
    declared_idempotency_key: str | None = None,
    requested_output_names: tuple[str, ...] = (),
    lease_id: str | None = None,
    lease_owner_id: str | None = None,
    fencing_token: int | None = None,
) -> RunCommand:
    return RunCommand(
        command_id=command_id,
        run_id=run_id,
        command_type=command_type,
        phase=phase,
        expected_revision=expected_revision,
        semantic_parameters=CanonicalJsonObject.from_object(semantic or {}),
        requested_output_names=requested_output_names,
        declared_idempotency_key=declared_idempotency_key,
        issued_at=issued_at or datetime(2026, 8, 6, 8, 0, tzinfo=UTC),
        actor_id="operator-1",
        lease_id=lease_id,
        lease_owner_id=lease_owner_id,
        fencing_token=fencing_token,
    )

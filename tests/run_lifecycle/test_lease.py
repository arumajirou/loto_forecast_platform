from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import make_command

from loto.run_lifecycle import (
    LeaseExpiredError,
    LeaseOwnershipError,
    StaleFencingTokenError,
)


def test_acquire_renew_expiry_takeover_and_fencing(service, clock) -> None:
    manager = service.lease_manager
    first = manager.acquire(
        run_id="run-001",
        lease_id="lease-a",
        owner_id="worker-a",
        ttl=timedelta(seconds=10),
    )
    assert first.fencing_token == 1
    with pytest.raises(LeaseOwnershipError):
        manager.acquire(
            run_id="run-001",
            lease_id="lease-b",
            owner_id="worker-b",
            ttl=timedelta(seconds=10),
        )
    clock.advance(timedelta(seconds=5))
    renewed = manager.heartbeat(
        run_id="run-001",
        lease_id="lease-a",
        owner_id="worker-a",
        ttl=timedelta(seconds=10),
    )
    assert renewed.heartbeat_at == clock.now()
    with pytest.raises(LeaseOwnershipError):
        manager.heartbeat(
            run_id="run-001",
            lease_id="lease-a",
            owner_id="worker-wrong",
            ttl=timedelta(seconds=10),
        )
    clock.advance(timedelta(seconds=11))
    with pytest.raises(LeaseExpiredError):
        manager.heartbeat(
            run_id="run-001",
            lease_id="lease-a",
            owner_id="worker-a",
            ttl=timedelta(seconds=10),
        )
    takeover = manager.acquire(
        run_id="run-001",
        lease_id="lease-b",
        owner_id="worker-b",
        ttl=timedelta(seconds=10),
    )
    assert takeover.fencing_token == 2
    with pytest.raises(StaleFencingTokenError):
        manager.assert_mutation_allowed(
            run_id="run-001",
            lease_id="lease-b",
            owner_id="worker-b",
            fencing_token=1,
        )


def test_stale_worker_mutation_is_rejected_by_service(service, clock) -> None:
    first = service.lease_manager.acquire(
        run_id="run-001",
        lease_id="lease-a",
        owner_id="worker-a",
        ttl=timedelta(seconds=2),
    )
    clock.advance(timedelta(seconds=3))
    service.lease_manager.acquire(
        run_id="run-001",
        lease_id="lease-b",
        owner_id="worker-b",
        ttl=timedelta(seconds=10),
    )
    with pytest.raises((LeaseOwnershipError, StaleFencingTokenError)):
        service.execute(
            make_command(
                command_id="stale",
                lease_id=first.lease_id,
                lease_owner_id=first.owner_id,
                fencing_token=first.fencing_token,
            )
        )

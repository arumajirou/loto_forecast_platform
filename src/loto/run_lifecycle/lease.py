"""Lease, heartbeat, takeover, and fencing-token controls."""

from __future__ import annotations

from datetime import timedelta

from .clock import Clock
from .exceptions import LeaseExpiredError, LeaseOwnershipError, StaleFencingTokenError
from .models import RunLease
from .repository import InMemoryLifecycleRepository


class LeaseManager:
    def __init__(self, repository: InMemoryLifecycleRepository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    def acquire(
        self,
        *,
        run_id: str,
        lease_id: str,
        owner_id: str,
        ttl: timedelta,
    ) -> RunLease:
        self._require_positive_ttl(ttl)
        now = self._clock.now()
        existing = self._repository.get_lease(run_id)
        if existing is not None and now < existing.expires_at:
            raise LeaseOwnershipError("an unexpired lease already owns this run")
        token = self._repository.next_fencing_token(run_id)
        lease = RunLease(
            run_id=run_id,
            lease_id=lease_id,
            owner_id=owner_id,
            acquired_at=now,
            heartbeat_at=now,
            expires_at=now + ttl,
            fencing_token=token,
        )
        self._repository.save_lease(lease)
        return lease

    def renew(
        self,
        *,
        run_id: str,
        lease_id: str,
        owner_id: str,
        ttl: timedelta,
    ) -> RunLease:
        self._require_positive_ttl(ttl)
        lease = self._require_live_owner(run_id, lease_id, owner_id)
        now = self._clock.now()
        renewed = lease.model_copy(update={"heartbeat_at": now, "expires_at": now + ttl})
        self._repository.save_lease(renewed)
        return renewed

    def heartbeat(
        self,
        *,
        run_id: str,
        lease_id: str,
        owner_id: str,
        ttl: timedelta,
    ) -> RunLease:
        return self.renew(run_id=run_id, lease_id=lease_id, owner_id=owner_id, ttl=ttl)

    def assert_mutation_allowed(
        self,
        *,
        run_id: str,
        lease_id: str,
        owner_id: str,
        fencing_token: int,
    ) -> RunLease:
        lease = self._require_live_owner(run_id, lease_id, owner_id)
        latest = self._repository.latest_fencing_token(run_id)
        if fencing_token != lease.fencing_token or fencing_token != latest:
            raise StaleFencingTokenError(
                f"fencing token {fencing_token} does not match active token {latest}"
            )
        return lease

    def _require_live_owner(self, run_id: str, lease_id: str, owner_id: str) -> RunLease:
        lease = self._repository.get_lease(run_id)
        if lease is None:
            raise LeaseOwnershipError("run has no lease")
        if lease.run_id != run_id:
            raise LeaseOwnershipError("lease is bound to another run")
        if lease.lease_id != lease_id:
            raise LeaseOwnershipError("wrong lease_id")
        if lease.owner_id != owner_id:
            raise LeaseOwnershipError("wrong lease owner")
        if self._clock.now() >= lease.expires_at:
            raise LeaseExpiredError("lease has expired")
        return lease

    @staticmethod
    def _require_positive_ttl(ttl: timedelta) -> None:
        if ttl.total_seconds() <= 0:
            raise ValueError("lease ttl must be positive")

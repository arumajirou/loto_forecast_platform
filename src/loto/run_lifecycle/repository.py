"""Thread-safe in-memory repository for foundation tests and examples."""

from __future__ import annotations

from threading import RLock

from .exceptions import (
    IdempotencyConflictError,
    OptimisticConcurrencyError,
    RepositoryConflictError,
    StaleFencingTokenError,
)
from .models import IdempotencyRecord, RunAggregate, RunEvent, RunLease


class InMemoryLifecycleRepository:
    """Atomic in-process store; it is not proof of database durability."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._aggregates: dict[str, RunAggregate] = {}
        self._events: dict[str, tuple[RunEvent, ...]] = {}
        self._idempotency: dict[str, IdempotencyRecord] = {}
        self._leases: dict[str, RunLease] = {}
        self._fencing_counters: dict[str, int] = {}

    def get_or_create_aggregate(self, run_id: str) -> RunAggregate:
        with self._lock:
            aggregate = self._aggregates.get(run_id)
            if aggregate is None:
                aggregate = RunAggregate.initial(run_id)
                self._aggregates[run_id] = aggregate
                self._events[run_id] = ()
            return aggregate

    def get_aggregate(self, run_id: str) -> RunAggregate | None:
        with self._lock:
            return self._aggregates.get(run_id)

    def list_events(self, run_id: str) -> tuple[RunEvent, ...]:
        with self._lock:
            return self._events.get(run_id, ())

    def get_idempotency(self, key: str) -> IdempotencyRecord | None:
        with self._lock:
            return self._idempotency.get(key)

    def replace_idempotency(self, record: IdempotencyRecord) -> None:
        with self._lock:
            existing = self._idempotency.get(record.idempotency_key)
            if existing is None:
                raise RepositoryConflictError("idempotency record disappeared")
            if existing.command_fingerprint_sha256 != record.command_fingerprint_sha256:
                raise IdempotencyConflictError("idempotency fingerprint changed")
            self._idempotency[record.idempotency_key] = record

    def commit_command(
        self,
        *,
        event: RunEvent,
        aggregate: RunAggregate,
        idempotency_record: IdempotencyRecord,
        expected_revision: int,
        fencing_token: int | None,
    ) -> None:
        """Atomically append event, update aggregate and store idempotency result."""

        with self._lock:
            current = self._aggregates.get(event.run_id) or RunAggregate.initial(event.run_id)
            if current.revision != expected_revision:
                raise OptimisticConcurrencyError(
                    f"expected revision {expected_revision}, current {current.revision}"
                )
            if event.sequence != current.revision + 1:
                raise RepositoryConflictError("event sequence is not the next revision")
            if event.previous_event_sha256 != current.last_event_sha256:
                raise RepositoryConflictError("event chain head changed before commit")
            existing = self._idempotency.get(idempotency_record.idempotency_key)
            if existing is not None:
                if existing.command_fingerprint_sha256 != (
                    idempotency_record.command_fingerprint_sha256
                ):
                    raise IdempotencyConflictError("idempotency key reused with another payload")
                raise RepositoryConflictError("semantic command was committed concurrently")
            if fencing_token is not None:
                latest = self._fencing_counters.get(event.run_id, 0)
                if fencing_token != latest:
                    raise StaleFencingTokenError(
                        f"fencing token {fencing_token} is stale; latest is {latest}"
                    )
            self._events[event.run_id] = self._events.get(event.run_id, ()) + (event,)
            self._aggregates[event.run_id] = aggregate
            self._idempotency[idempotency_record.idempotency_key] = idempotency_record

    def get_lease(self, run_id: str) -> RunLease | None:
        with self._lock:
            return self._leases.get(run_id)

    def save_lease(self, lease: RunLease) -> None:
        with self._lock:
            self._leases[lease.run_id] = lease
            self._fencing_counters[lease.run_id] = max(
                lease.fencing_token,
                self._fencing_counters.get(lease.run_id, 0),
            )

    def next_fencing_token(self, run_id: str) -> int:
        with self._lock:
            token = self._fencing_counters.get(run_id, 0) + 1
            self._fencing_counters[run_id] = token
            return token

    def latest_fencing_token(self, run_id: str) -> int:
        with self._lock:
            return self._fencing_counters.get(run_id, 0)

    def counts(self, run_id: str) -> tuple[int, int]:
        with self._lock:
            events = len(self._events.get(run_id, ()))
            records = sum(record.run_id == run_id for record in self._idempotency.values())
            return events, records

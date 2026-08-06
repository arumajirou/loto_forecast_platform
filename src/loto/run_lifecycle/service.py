"""Lifecycle command service with idempotency, leases, and atomic event commit."""

from __future__ import annotations

from collections.abc import Callable
from threading import RLock

from .canonical import sha256_canonical
from .clock import Clock
from .events import build_event
from .exceptions import IdempotencyConflictError, TransitionRejected
from .idempotency import (
    compute_command_fingerprint,
    effective_idempotency_key,
)
from .lease import LeaseManager
from .models import (
    CanonicalJsonObject,
    CommandExecutionResult,
    DuplicateCommandEvidence,
    EffectResult,
    HashBinding,
    IdempotencyRecord,
    LifecycleSnapshot,
    RunAggregate,
    RunCommand,
    RunPhase,
    RunStatus,
)
from .repository import InMemoryLifecycleRepository
from .transitions import TransitionEngine

EffectHandler = Callable[[RunAggregate], EffectResult]


class LifecycleService:
    """Single-process foundation service; database durability is intentionally out of scope."""

    def __init__(
        self,
        repository: InMemoryLifecycleRepository,
        clock: Clock,
        *,
        transition_engine: TransitionEngine | None = None,
        lease_manager: LeaseManager | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._transition_engine = transition_engine or TransitionEngine()
        self._lease_manager = lease_manager or LeaseManager(repository, clock)
        self._lock = RLock()

    @property
    def lease_manager(self) -> LeaseManager:
        return self._lease_manager

    def execute(
        self,
        command: RunCommand,
        effect: EffectHandler | None = None,
    ) -> CommandExecutionResult:
        """Execute one semantic command at most once within this service instance."""

        with self._lock:
            idempotency_key = effective_idempotency_key(command)
            fingerprint = compute_command_fingerprint(command)
            existing = self._repository.get_idempotency(idempotency_key)
            if existing is not None:
                return self._return_duplicate(command, existing, fingerprint)

            aggregate = self._repository.get_or_create_aggregate(command.run_id)
            if command.lease_id is not None:
                self._lease_manager.assert_mutation_allowed(
                    run_id=command.run_id,
                    lease_id=command.lease_id,
                    owner_id=command.lease_owner_id or "",
                    fencing_token=command.fencing_token or 0,
                )
            decision = self._transition_engine.decide(aggregate, command)
            if not decision.allowed:
                raise TransitionRejected(decision.reason_code)

            now = self._clock.now()
            preserved_names = self._already_sealed_requested_outputs(aggregate, command)
            if preserved_names:
                effect_result = EffectResult(
                    payload=CanonicalJsonObject.from_object(
                        {
                            "outcome": "OUTPUTS_ALREADY_SEALED",
                            "preserved_output_names": list(preserved_names),
                        }
                    )
                )
                effect_executed = False
            elif effect is not None:
                effect_result = effect(aggregate)
                effect_executed = True
            else:
                effect_result = EffectResult()
                effect_executed = False

            merged_outputs = self._merge_outputs(
                aggregate.immutable_output_hashes,
                effect_result.sealed_outputs,
            )
            event = build_event(
                aggregate=aggregate,
                command=command,
                decision=decision,
                idempotency_key=idempotency_key,
                occurred_at=now,
                payload=effect_result.payload,
                sealed_outputs=effect_result.sealed_outputs,
                evidence_references=effect_result.evidence_references,
            )
            cancelled_at = now if event.status == RunStatus.CANCELLED else aggregate.cancelled_at
            completed_at = (
                now
                if event.phase == RunPhase.COMPLETE and event.status == RunStatus.SUCCEEDED
                else aggregate.completed_at
            )
            new_aggregate = RunAggregate(
                run_id=aggregate.run_id,
                phase=event.phase,
                status=event.status,
                revision=event.revision,
                last_event_sha256=event.event_sha256,
                immutable_output_hashes=merged_outputs,
                cancelled_at=cancelled_at,
                completed_at=completed_at,
            )
            result_payload = CanonicalJsonObject.from_object(
                {
                    "aggregate_revision": new_aggregate.revision,
                    "effect_executed": effect_executed,
                    "event_sha256": event.event_sha256,
                    "payload": effect_result.payload.as_object(),
                }
            )
            record = IdempotencyRecord(
                idempotency_key=idempotency_key,
                run_id=command.run_id,
                command_fingerprint_sha256=fingerprint,
                result_snapshot_sha256=sha256_canonical(result_payload.as_object()),
                result_snapshot=result_payload,
                processed_at=now,
            )
            self._repository.commit_command(
                event=event,
                aggregate=new_aggregate,
                idempotency_record=record,
                expected_revision=command.expected_revision,
                fencing_token=command.fencing_token,
            )
            return CommandExecutionResult(
                run_id=command.run_id,
                idempotency_key=idempotency_key,
                duplicate=False,
                effect_executed=effect_executed,
                event=event,
                aggregate=new_aggregate,
                payload=result_payload,
            )

    def snapshot(self, run_id: str) -> LifecycleSnapshot:
        aggregate = self._repository.get_or_create_aggregate(run_id)
        events, records = self._repository.counts(run_id)
        return LifecycleSnapshot.create(
            aggregate=aggregate,
            event_count=events,
            idempotency_record_count=records,
            captured_at=self._clock.now(),
        )

    def _return_duplicate(
        self,
        command: RunCommand,
        existing: IdempotencyRecord,
        fingerprint: str,
    ) -> CommandExecutionResult:
        if existing.command_fingerprint_sha256 != fingerprint:
            raise IdempotencyConflictError(
                "same idempotency key was declared for a different semantic command"
            )
        observation = DuplicateCommandEvidence(
            command_id=command.command_id,
            observed_at=self._clock.now(),
            command_fingerprint_sha256=fingerprint,
        )
        updated = existing.model_copy(
            update={
                "duplicate_count": existing.duplicate_count + 1,
                "duplicate_observations": existing.duplicate_observations + (observation,),
            }
        )
        self._repository.replace_idempotency(updated)
        aggregate = self._repository.get_or_create_aggregate(command.run_id)
        return CommandExecutionResult(
            run_id=command.run_id,
            idempotency_key=existing.idempotency_key,
            duplicate=True,
            effect_executed=False,
            event=None,
            aggregate=aggregate,
            payload=existing.result_snapshot,
        )

    @staticmethod
    def _already_sealed_requested_outputs(
        aggregate: RunAggregate,
        command: RunCommand,
    ) -> tuple[str, ...]:
        if not command.requested_output_names:
            return ()
        existing = {item.name for item in aggregate.immutable_output_hashes}
        requested = set(command.requested_output_names)
        if requested.issubset(existing):
            return tuple(sorted(requested))
        return ()

    @staticmethod
    def _merge_outputs(
        existing: tuple[HashBinding, ...],
        added: tuple[HashBinding, ...],
    ) -> tuple[HashBinding, ...]:
        merged = {item.name: item.sha256 for item in existing}
        for item in added:
            previous = merged.get(item.name)
            if previous is not None and previous != item.sha256:
                raise IdempotencyConflictError(
                    f"sealed output {item.name!r} cannot be regenerated with another hash"
                )
            merged[item.name] = item.sha256
        return tuple(
            HashBinding(name=name, sha256=sha256) for name, sha256 in sorted(merged.items())
        )

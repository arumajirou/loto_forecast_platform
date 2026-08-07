"""Strict immutable lifecycle contracts."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .canonical import canonical_json, parse_canonical_object, sha256_canonical

SCHEMA_VERSION = "1.0.0"

SafeIdentifier = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]


class StrictFrozenModel(BaseModel):
    """Base class for evidence contracts."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
        allow_inf_nan=False,
    )


class RunPhase(str, Enum):
    PLAN = "PLAN"
    DATA = "DATA"
    TRAIN = "TRAIN"
    PREDICT = "PREDICT"
    LOCK = "LOCK"
    WAIT_ACTUAL = "WAIT_ACTUAL"
    READ_ACTUAL = "READ_ACTUAL"
    SCORE = "SCORE"
    PERSIST = "PERSIST"
    PROMOTE = "PROMOTE"
    COMPLETE = "COMPLETE"


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"


class RunCommandType(str, Enum):
    START = "START"
    MARK_SUCCEEDED = "MARK_SUCCEEDED"
    MARK_RETRYABLE_FAILURE = "MARK_RETRYABLE_FAILURE"
    MARK_BLOCKED = "MARK_BLOCKED"
    MARK_TIMED_OUT = "MARK_TIMED_OUT"
    MARK_TERMINAL_FAILURE = "MARK_TERMINAL_FAILURE"
    RETRY = "RETRY"
    RESUME = "RESUME"
    CANCEL = "CANCEL"


class FindingSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class CanonicalJsonObject(StrictFrozenModel):
    """Immutable canonical JSON-object carrier."""

    text: str = "{}"

    @field_validator("text")
    @classmethod
    def canonical_object_required(cls, value: str) -> str:
        try:
            parse_canonical_object(value)
        except Exception as exc:
            raise ValueError(str(exc)) from exc
        return value

    @classmethod
    def from_object(cls, value: dict[str, object]) -> "CanonicalJsonObject":
        return cls(text=canonical_json(value))

    def as_object(self) -> dict[str, object]:
        return parse_canonical_object(self.text)


class HashBinding(StrictFrozenModel):
    name: SafeIdentifier
    sha256: Sha256


class EvidenceReference(StrictFrozenModel):
    evidence_type: SafeIdentifier
    evidence_id: SafeIdentifier
    evidence_sha256: Sha256
    schema_version: SafeIdentifier
    producer_identity: SafeIdentifier


class DecisionEvidence(StrictFrozenModel):
    key: SafeIdentifier
    value: str = Field(min_length=1, max_length=512)


class RunCommand(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    command_id: SafeIdentifier
    run_id: SafeIdentifier
    command_type: RunCommandType
    phase: RunPhase
    expected_revision: NonNegativeInt
    subject_hashes: tuple[HashBinding, ...] = ()
    semantic_parameters: CanonicalJsonObject = CanonicalJsonObject()
    requested_output_names: tuple[SafeIdentifier, ...] = ()
    declared_idempotency_key: Sha256 | None = None
    issued_at: datetime
    actor_id: SafeIdentifier
    lease_id: SafeIdentifier | None = None
    lease_owner_id: SafeIdentifier | None = None
    fencing_token: PositiveInt | None = None

    @field_validator("issued_at")
    @classmethod
    def issued_at_must_be_utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def lease_fields_are_all_or_none(self) -> "RunCommand":
        provided = (
            self.lease_id is not None,
            self.lease_owner_id is not None,
            self.fencing_token is not None,
        )
        if any(provided) and not all(provided):
            raise ValueError("lease_id, lease_owner_id and fencing_token must be supplied together")
        if len(set(self.requested_output_names)) != len(self.requested_output_names):
            raise ValueError("requested_output_names must be unique")
        if len({item.name for item in self.subject_hashes}) != len(self.subject_hashes):
            raise ValueError("subject_hashes names must be unique")
        return self


class TransitionRule(StrictFrozenModel):
    rule_id: SafeIdentifier
    from_phase: RunPhase
    from_status: RunStatus
    command_type: RunCommandType
    to_phase: RunPhase
    to_status: RunStatus
    description: str = Field(min_length=1, max_length=512)


class TransitionDecision(StrictFrozenModel):
    allowed: bool
    reason_code: SafeIdentifier
    current_phase: RunPhase
    current_status: RunStatus
    current_revision: NonNegativeInt
    expected_revision: NonNegativeInt
    target_phase: RunPhase | None = None
    target_status: RunStatus | None = None
    rule_id: SafeIdentifier | None = None
    evidence: tuple[DecisionEvidence, ...] = ()


class RunEvent(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    run_id: SafeIdentifier
    sequence: PositiveInt
    revision: PositiveInt
    expected_revision: NonNegativeInt
    command_id: SafeIdentifier
    command_type: RunCommandType
    idempotency_key: Sha256
    phase: RunPhase
    status: RunStatus
    occurred_at: datetime
    previous_event_sha256: Sha256 | None
    payload: CanonicalJsonObject = CanonicalJsonObject()
    sealed_outputs: tuple[HashBinding, ...] = ()
    evidence_references: tuple[EvidenceReference, ...] = ()
    event_sha256: Sha256

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_must_be_utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def event_sequence_contract(self) -> "RunEvent":
        if self.revision != self.sequence:
            raise ValueError("event revision must equal sequence")
        if self.expected_revision != self.revision - 1:
            raise ValueError("expected_revision must equal revision - 1")
        if self.sequence == 1 and self.previous_event_sha256 is not None:
            raise ValueError("first event must not have a previous hash")
        if self.sequence > 1 and self.previous_event_sha256 is None:
            raise ValueError("non-first event requires previous_event_sha256")
        if len({item.name for item in self.sealed_outputs}) != len(self.sealed_outputs):
            raise ValueError("sealed output names must be unique per event")
        return self


class RunLease(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    run_id: SafeIdentifier
    lease_id: SafeIdentifier
    owner_id: SafeIdentifier
    acquired_at: datetime
    heartbeat_at: datetime
    expires_at: datetime
    fencing_token: PositiveInt

    @field_validator("acquired_at", "heartbeat_at", "expires_at")
    @classmethod
    def lease_times_must_be_utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def lease_time_order(self) -> "RunLease":
        if self.heartbeat_at < self.acquired_at:
            raise ValueError("heartbeat_at cannot precede acquired_at")
        if self.expires_at <= self.heartbeat_at:
            raise ValueError("expires_at must follow heartbeat_at")
        return self


class RunAggregate(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    run_id: SafeIdentifier
    phase: RunPhase = RunPhase.PLAN
    status: RunStatus = RunStatus.PENDING
    revision: NonNegativeInt = 0
    last_event_sha256: Sha256 | None = None
    immutable_output_hashes: tuple[HashBinding, ...] = ()
    cancelled_at: datetime | None = None
    completed_at: datetime | None = None

    @field_validator("cancelled_at", "completed_at")
    @classmethod
    def optional_times_must_be_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _require_utc(value)

    @model_validator(mode="after")
    def aggregate_consistency(self) -> "RunAggregate":
        if self.revision == 0 and self.last_event_sha256 is not None:
            raise ValueError("revision zero cannot have an event-chain head")
        if self.revision > 0 and self.last_event_sha256 is None:
            raise ValueError("nonzero revision requires an event-chain head")
        if len({item.name for item in self.immutable_output_hashes}) != len(
            self.immutable_output_hashes
        ):
            raise ValueError("immutable output names must be unique")
        if self.status == RunStatus.CANCELLED and self.cancelled_at is None:
            raise ValueError("cancelled aggregate requires cancelled_at")
        if self.phase == RunPhase.COMPLETE and self.status == RunStatus.SUCCEEDED:
            if self.completed_at is None:
                raise ValueError("completed aggregate requires completed_at")
        return self

    @classmethod
    def initial(cls, run_id: str) -> "RunAggregate":
        return cls(run_id=run_id)


class DuplicateCommandEvidence(StrictFrozenModel):
    command_id: SafeIdentifier
    observed_at: datetime
    command_fingerprint_sha256: Sha256

    @field_validator("observed_at")
    @classmethod
    def observed_at_must_be_utc(cls, value: datetime) -> datetime:
        return _require_utc(value)


class IdempotencyRecord(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    idempotency_key: Sha256
    run_id: SafeIdentifier
    command_fingerprint_sha256: Sha256
    result_snapshot_sha256: Sha256
    result_snapshot: CanonicalJsonObject
    processed_at: datetime
    duplicate_count: NonNegativeInt = 0
    duplicate_observations: tuple[DuplicateCommandEvidence, ...] = ()

    @field_validator("processed_at")
    @classmethod
    def processed_at_must_be_utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def duplicate_count_matches_observations(self) -> "IdempotencyRecord":
        if self.duplicate_count != len(self.duplicate_observations):
            raise ValueError("duplicate_count must equal duplicate_observations length")
        return self


class LifecycleValidationFinding(StrictFrozenModel):
    code: SafeIdentifier
    severity: FindingSeverity
    message: str = Field(min_length=1, max_length=1000)
    event_sequence: PositiveInt | None = None


class LifecycleValidationReport(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    valid: bool
    findings: tuple[LifecycleValidationFinding, ...]
    validated_event_count: NonNegativeInt
    chain_head_sha256: Sha256 | None

    @model_validator(mode="after")
    def valid_flag_matches_findings(self) -> "LifecycleValidationReport":
        has_error = any(item.severity == FindingSeverity.ERROR for item in self.findings)
        if self.valid == has_error:
            raise ValueError("valid must be the inverse of ERROR findings")
        return self


class LifecycleSnapshot(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    aggregate: RunAggregate
    event_count: NonNegativeInt
    idempotency_record_count: NonNegativeInt
    captured_at: datetime
    snapshot_sha256: Sha256

    @field_validator("captured_at")
    @classmethod
    def captured_at_must_be_utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @classmethod
    def create(
        cls,
        *,
        aggregate: RunAggregate,
        event_count: int,
        idempotency_record_count: int,
        captured_at: datetime,
    ) -> "LifecycleSnapshot":
        payload = {
            "schema_version": SCHEMA_VERSION,
            "aggregate": aggregate,
            "event_count": event_count,
            "idempotency_record_count": idempotency_record_count,
            "captured_at": captured_at,
        }
        return cls(snapshot_sha256=sha256_canonical(payload), **payload)


class EffectResult(StrictFrozenModel):
    payload: CanonicalJsonObject = CanonicalJsonObject()
    sealed_outputs: tuple[HashBinding, ...] = ()
    evidence_references: tuple[EvidenceReference, ...] = ()


class CommandExecutionResult(StrictFrozenModel):
    run_id: SafeIdentifier
    idempotency_key: Sha256
    duplicate: bool
    effect_executed: bool
    event: RunEvent | None
    aggregate: RunAggregate
    payload: CanonicalJsonObject


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("datetime must be timezone-aware UTC")
    return value

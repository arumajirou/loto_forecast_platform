"""Strict immutable contracts for host clock operational health evidence."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticUndefined

from .canonical import sha256_canonical, verified_hash_payload

SCHEMA_VERSION = "1.0.0"
SafeIdentifier = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonNegativeFloat = Annotated[float, Field(ge=0)]
PositiveFloat = Annotated[float, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]


class StrictFrozenModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
        allow_inf_nan=False,
    )


class ClockHealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class LeapStatus(str, Enum):
    NORMAL = "NORMAL"
    INSERT_SECOND = "INSERT_SECOND"
    DELETE_SECOND = "DELETE_SECOND"
    NOT_SYNCHRONIZED = "NOT_SYNCHRONIZED"
    UNKNOWN = "UNKNOWN"


class CheckOutcome(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class SourceSelectionState(str, Enum):
    CURRENT = "CURRENT"
    COMBINED = "COMBINED"
    EXCLUDED = "EXCLUDED"
    UNREACHABLE = "UNREACHABLE"
    FALSETICKER = "FALSETICKER"
    UNKNOWN = "UNKNOWN"


class ClockCommandEvidence(StrictFrozenModel):
    command_id: SafeIdentifier
    argv: tuple[str, ...]
    started_at_utc: datetime
    duration_seconds: NonNegativeFloat
    exit_code: int | None
    timed_out: bool
    stdout_sha256: Sha256
    stderr_sha256: Sha256
    stdout_size_bytes: NonNegativeInt
    stderr_size_bytes: NonNegativeInt

    @field_validator("started_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def command_contract(self) -> "ClockCommandEvidence":
        if not self.argv:
            raise ValueError("argv must not be empty")
        if any(not item or len(item) > 256 or "\x00" in item for item in self.argv):
            raise ValueError("argv entries must be bounded non-empty strings")
        if self.timed_out and self.exit_code is not None:
            raise ValueError("timed-out command must not claim an exit code")
        if not self.timed_out and self.exit_code is None:
            raise ValueError("completed command requires an exit code")
        return self


class ClockParserEvidence(StrictFrozenModel):
    parser_id: SafeIdentifier
    parser_version: SafeIdentifier
    parser_code_sha256: Sha256
    raw_tracking_sha256: Sha256
    raw_sources_sha256: Sha256
    raw_tracking_size_bytes: NonNegativeInt
    raw_sources_size_bytes: NonNegativeInt
    commands: tuple[ClockCommandEvidence, ...] = ()
    parse_errors: tuple[str, ...] = ()

    @field_validator("parse_errors")
    @classmethod
    def bounded_parse_errors(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) > 16:
            raise ValueError("at most 16 parse errors are retained")
        for item in value:
            if not item or len(item) > 256:
                raise ValueError("parse errors must be non-empty and at most 256 characters")
        return value

    @model_validator(mode="after")
    def command_identity_contract(self) -> "ClockParserEvidence":
        identifiers = [item.command_id for item in self.commands]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("parser command identifiers must be unique")
        return self


class ClockSourceObservation(StrictFrozenModel):
    source_id_sha256: Sha256
    selection_state: SourceSelectionState
    online: bool
    selected: bool
    stratum: NonNegativeInt | None = None
    poll_interval_seconds: NonNegativeFloat | None = None
    sample_age_seconds: NonNegativeFloat | None = None
    offset_seconds: float | None = None
    uncertainty_seconds: NonNegativeFloat | None = None

    @model_validator(mode="after")
    def source_consistency(self) -> "ClockSourceObservation":
        if self.selected and not self.online:
            raise ValueError("selected source must be online")
        if self.selection_state == SourceSelectionState.CURRENT and not self.selected:
            raise ValueError("CURRENT source must be selected")
        return self


class ClockContinuityEvidence(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    sample_id: SafeIdentifier
    started_at_utc: datetime
    ended_at_utc: datetime
    wall_delta_ns: NonNegativeInt
    monotonic_delta_ns: NonNegativeInt
    difference_ns: NonNegativeInt
    step_threshold_ns: PositiveInt
    clock_step_detected: bool
    continuity_sha256: Sha256

    @field_validator("started_at_utc", "ended_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def continuity_contract(self) -> "ClockContinuityEvidence":
        if self.ended_at_utc < self.started_at_utc:
            raise ValueError("continuity end cannot precede start")
        expected_difference = abs(self.wall_delta_ns - self.monotonic_delta_ns)
        if self.difference_ns != expected_difference:
            raise ValueError("difference_ns does not match wall/monotonic deltas")
        if self.clock_step_detected != (self.difference_ns > self.step_threshold_ns):
            raise ValueError("clock_step_detected does not match threshold comparison")
        expected_hash = sha256_canonical(verified_hash_payload(self, "continuity_sha256"))
        if self.continuity_sha256 != expected_hash:
            raise ValueError("continuity_sha256 mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        sample_id: str,
        started_at_utc: datetime,
        ended_at_utc: datetime,
        wall_delta_ns: int,
        monotonic_delta_ns: int,
        step_threshold_ns: int,
    ) -> "ClockContinuityEvidence":
        payload = {
            "sample_id": sample_id,
            "started_at_utc": started_at_utc,
            "ended_at_utc": ended_at_utc,
            "wall_delta_ns": wall_delta_ns,
            "monotonic_delta_ns": monotonic_delta_ns,
            "difference_ns": abs(wall_delta_ns - monotonic_delta_ns),
            "step_threshold_ns": step_threshold_ns,
            "clock_step_detected": abs(wall_delta_ns - monotonic_delta_ns) > step_threshold_ns,
        }
        return cls(
            **payload,
            continuity_sha256=sha256_canonical({"schema_version": SCHEMA_VERSION, **payload}),
        )


class ClockObservation(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    observation_id: SafeIdentifier
    observed_at_utc: datetime
    synchronized: bool | None
    leap_status: LeapStatus
    stratum: NonNegativeInt | None
    last_offset_seconds: float | None
    rms_offset_seconds: NonNegativeFloat | None
    root_delay_seconds: NonNegativeFloat | None
    root_dispersion_seconds: NonNegativeFloat | None
    skew_ppm: NonNegativeFloat | None
    online_source_count: NonNegativeInt | None
    sample_age_seconds: NonNegativeFloat | None
    sources: tuple[ClockSourceObservation, ...] = ()
    continuity: ClockContinuityEvidence | None = None
    parser_evidence: ClockParserEvidence
    observation_sha256: Sha256

    @field_validator("observed_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def observation_contract(self) -> "ClockObservation":
        source_ids = [source.source_id_sha256 for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("clock source identities must be unique")
        if sum(source.selected for source in self.sources) > 1:
            raise ValueError("at most one clock source may be selected")
        if self.online_source_count is not None:
            actual_online = sum(source.online for source in self.sources)
            if self.sources and self.online_source_count != actual_online:
                raise ValueError("online_source_count does not match source observations")
        expected = sha256_canonical(verified_hash_payload(self, "observation_sha256"))
        if self.observation_sha256 != expected:
            raise ValueError("observation_sha256 mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> "ClockObservation":
        payload = {"schema_version": SCHEMA_VERSION, **values}
        return cls(
            **payload,
            observation_sha256=sha256_canonical(payload),
        )


class ClockHealthPolicy(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    policy_id: SafeIdentifier
    require_synchronized: bool = True
    require_continuity: bool = True
    allowed_leap_statuses: tuple[LeapStatus, ...] = (LeapStatus.NORMAL,)
    warning_leap_statuses: tuple[LeapStatus, ...] = (
        LeapStatus.INSERT_SECOND,
        LeapStatus.DELETE_SECOND,
    )
    max_stratum_warning: PositiveInt = 4
    max_stratum_block: PositiveInt = 8
    max_abs_last_offset_warning_seconds: PositiveFloat = 0.005
    max_abs_last_offset_block_seconds: PositiveFloat = 0.050
    max_rms_offset_warning_seconds: PositiveFloat = 0.005
    max_rms_offset_block_seconds: PositiveFloat = 0.050
    max_root_delay_warning_seconds: PositiveFloat = 0.100
    max_root_delay_block_seconds: PositiveFloat = 0.500
    max_root_dispersion_warning_seconds: PositiveFloat = 0.010
    max_root_dispersion_block_seconds: PositiveFloat = 0.100
    max_skew_warning_ppm: PositiveFloat = 50.0
    max_skew_block_ppm: PositiveFloat = 200.0
    min_online_sources_healthy: PositiveInt = 2
    max_sample_age_warning_seconds: PositiveFloat = 120.0
    max_sample_age_block_seconds: PositiveFloat = 600.0
    continuity_step_threshold_ns: PositiveInt = 250_000_000
    policy_sha256: Sha256

    @model_validator(mode="after")
    def policy_contract(self) -> "ClockHealthPolicy":
        pairs = (
            (self.max_stratum_warning, self.max_stratum_block, "stratum"),
            (
                self.max_abs_last_offset_warning_seconds,
                self.max_abs_last_offset_block_seconds,
                "last_offset",
            ),
            (
                self.max_rms_offset_warning_seconds,
                self.max_rms_offset_block_seconds,
                "rms_offset",
            ),
            (
                self.max_root_delay_warning_seconds,
                self.max_root_delay_block_seconds,
                "root_delay",
            ),
            (
                self.max_root_dispersion_warning_seconds,
                self.max_root_dispersion_block_seconds,
                "root_dispersion",
            ),
            (self.max_skew_warning_ppm, self.max_skew_block_ppm, "skew"),
            (
                self.max_sample_age_warning_seconds,
                self.max_sample_age_block_seconds,
                "sample_age",
            ),
        )
        for warning, blocked, name in pairs:
            if warning > blocked:
                raise ValueError(f"{name} warning threshold cannot exceed block threshold")
        if len(set(self.allowed_leap_statuses)) != len(self.allowed_leap_statuses):
            raise ValueError("allowed_leap_statuses must be unique")
        if len(set(self.warning_leap_statuses)) != len(self.warning_leap_statuses):
            raise ValueError("warning_leap_statuses must be unique")
        if set(self.allowed_leap_statuses) & set(self.warning_leap_statuses):
            raise ValueError("allowed and warning leap statuses must be disjoint")
        expected = sha256_canonical(verified_hash_payload(self, "policy_sha256"))
        if self.policy_sha256 != expected:
            raise ValueError("policy_sha256 mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> "ClockHealthPolicy":
        allowed = set(cls.model_fields) - {"policy_sha256"}
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ValueError(f"unknown policy fields: {','.join(unknown)}")
        payload: dict[str, object] = {}
        for name, field in cls.model_fields.items():
            if name == "policy_sha256":
                continue
            if name in values:
                payload[name] = values[name]
            elif field.default is not PydanticUndefined:
                payload[name] = field.default
            elif field.default_factory is not None:
                payload[name] = field.default_factory()
        return cls(**payload, policy_sha256=sha256_canonical(payload))


class ClockCheckResult(StrictFrozenModel):
    check_id: SafeIdentifier
    outcome: CheckOutcome
    observed_value: str = Field(min_length=1, max_length=256)
    policy_value: str = Field(min_length=1, max_length=256)
    reason_code: SafeIdentifier


class ClockHealthDecision(StrictFrozenModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    decision_id: SafeIdentifier
    observation_sha256: Sha256
    policy_sha256: Sha256
    status: ClockHealthStatus
    checks: tuple[ClockCheckResult, ...]
    failed_checks: tuple[SafeIdentifier, ...]
    warning_checks: tuple[SafeIdentifier, ...]
    unknown_checks: tuple[SafeIdentifier, ...]
    clock_step_detected: bool
    prediction_lock_allowed: bool
    operational_precondition_only: Literal[True] = True
    external_trust_established: Literal[False] = False
    trusted_time_evidence_generated: Literal[False] = False
    signature_evidence_generated: Literal[False] = False
    evaluated_at_utc: datetime
    decision_sha256: Sha256

    @field_validator("evaluated_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def decision_contract(self) -> "ClockHealthDecision":
        check_ids = [item.check_id for item in self.checks]
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("clock check identifiers must be unique")
        failed = tuple(item.check_id for item in self.checks if item.outcome == CheckOutcome.FAIL)
        warnings = tuple(
            item.check_id for item in self.checks if item.outcome == CheckOutcome.WARNING
        )
        unknowns = tuple(
            item.check_id for item in self.checks if item.outcome == CheckOutcome.UNKNOWN
        )
        if self.failed_checks != failed:
            raise ValueError("failed_checks do not match check outcomes")
        if self.warning_checks != warnings:
            raise ValueError("warning_checks do not match check outcomes")
        if self.unknown_checks != unknowns:
            raise ValueError("unknown_checks do not match check outcomes")
        expected_status = _decision_status(failed, warnings, unknowns)
        if self.status != expected_status:
            raise ValueError("status does not match check outcomes")
        if self.prediction_lock_allowed != (self.status == ClockHealthStatus.HEALTHY):
            raise ValueError("prediction_lock_allowed is true only for HEALTHY")
        expected = sha256_canonical(verified_hash_payload(self, "decision_sha256"))
        if self.decision_sha256 != expected:
            raise ValueError("decision_sha256 mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        decision_id: str,
        observation_sha256: str,
        policy_sha256: str,
        checks: tuple[ClockCheckResult, ...],
        clock_step_detected: bool,
        evaluated_at_utc: datetime,
    ) -> "ClockHealthDecision":
        failed = tuple(item.check_id for item in checks if item.outcome == CheckOutcome.FAIL)
        warnings = tuple(item.check_id for item in checks if item.outcome == CheckOutcome.WARNING)
        unknowns = tuple(item.check_id for item in checks if item.outcome == CheckOutcome.UNKNOWN)
        status = _decision_status(failed, warnings, unknowns)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "decision_id": decision_id,
            "observation_sha256": observation_sha256,
            "policy_sha256": policy_sha256,
            "status": status,
            "checks": checks,
            "failed_checks": failed,
            "warning_checks": warnings,
            "unknown_checks": unknowns,
            "clock_step_detected": clock_step_detected,
            "prediction_lock_allowed": status == ClockHealthStatus.HEALTHY,
            "operational_precondition_only": True,
            "external_trust_established": False,
            "trusted_time_evidence_generated": False,
            "signature_evidence_generated": False,
            "evaluated_at_utc": evaluated_at_utc,
        }
        return cls(**payload, decision_sha256=sha256_canonical(payload))


def _decision_status(
    failed: tuple[str, ...],
    warnings: tuple[str, ...],
    unknowns: tuple[str, ...],
) -> ClockHealthStatus:
    if failed:
        return ClockHealthStatus.BLOCKED
    if unknowns:
        return ClockHealthStatus.UNKNOWN
    if warnings:
        return ClockHealthStatus.DEGRADED
    return ClockHealthStatus.HEALTHY


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("datetime must be timezone-aware UTC")
    return value

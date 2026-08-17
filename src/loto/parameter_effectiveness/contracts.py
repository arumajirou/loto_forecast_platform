"""Strict contracts for repeated parameter-effectiveness probes."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ParameterScope(StrEnum):
    """Where an argument is applied by a library adapter."""

    AUTO = "auto"
    MODEL_CONSTRUCTOR = "model_constructor"
    LIBRARY_CONSTRUCTOR = "library_constructor"
    FIT = "fit"
    PREDICT = "predict"


class EffectSurface(StrEnum):
    """Observable surface used to prove that an argument has an effect."""

    ACCEPTANCE = "acceptance"
    TRIAL_COUNT = "trial_count"
    HISTORY = "history"
    PREDICTION = "prediction"
    METRIC = "metric"
    RUNTIME = "runtime"


class ExpectedRelation(StrEnum):
    """Expected treatment/control relation on the selected surface."""

    CHANGE = "change"
    INCREASE = "increase"
    DECREASE = "decrease"
    INVARIANT = "invariant"


class EffectOutcome(StrEnum):
    """Normalized verdict for one parameter probe."""

    EFFECTIVE = "effective"
    ACCEPTED_NO_OBSERVABLE_EFFECT = "accepted_no_observable_effect"
    EXPECTATION_VIOLATED = "expectation_violated"
    INCONCLUSIVE = "inconclusive"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class ParameterProbeSpec(BaseModel):
    """One paired control/treatment parameter probe.

    The same seeds and repeats are applied to both values.  Effectiveness is
    never inferred from signature inspection or from a single successful fit.
    """

    model_config = ConfigDict(extra="forbid")

    probe_id: str = Field(min_length=1)
    library: str = Field(min_length=1)
    model: str = Field(min_length=1)
    parameter: str = Field(min_length=1)
    scope: ParameterScope = ParameterScope.AUTO
    control: Any
    treatment: Any
    expected_surface: EffectSurface
    expected_relation: ExpectedRelation = ExpectedRelation.CHANGE
    seeds: tuple[int, ...] = (1, 42, 1729, 20260730)
    repeats: int = Field(default=1, ge=1, le=100)
    min_match_fraction: float = Field(default=0.75, gt=0.0, le=1.0)
    absolute_tolerance: float = Field(default=1e-12, ge=0.0)
    relative_tolerance: float = Field(default=1e-9, ge=0.0)
    base_args: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_pairing(self) -> "ParameterProbeSpec":
        if len(self.seeds) < 2:
            raise ValueError("at least two seeds are required")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must be unique")
        if self.control == self.treatment:
            raise ValueError("control and treatment must differ")
        return self


class ParameterSuiteSpec(BaseModel):
    """Reusable collection of parameter probes."""

    model_config = ConfigDict(extra="forbid")

    suite_id: str = Field(min_length=1)
    probes: list[ParameterProbeSpec] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_probe_ids(self) -> "ParameterSuiteSpec":
        ids = [probe.probe_id for probe in self.probes]
        if len(ids) != len(set(ids)):
            raise ValueError("probe_id values must be unique within a suite")
        return self


ScalarObservable = int | float | bool | str | None


class ProbeRunObservation(BaseModel):
    """Normalized output from one adapter run."""

    model_config = ConfigDict(extra="forbid")

    accepted: bool
    success: bool
    finite: bool
    output_shape: tuple[int, ...] = ()
    prediction_sha256: str | None = None
    observables: dict[str, ScalarObservable] = Field(default_factory=dict)
    runtime_seconds: float = Field(ge=0.0)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def surface_value(self, surface: EffectSurface) -> ScalarObservable:
        if surface is EffectSurface.ACCEPTANCE:
            return self.accepted
        if surface is EffectSurface.PREDICTION:
            return self.prediction_sha256
        if surface is EffectSurface.RUNTIME:
            return self.runtime_seconds
        return self.observables.get(surface.value)


class PairedProbeObservation(BaseModel):
    """Control and treatment executed with the same seed/repeat."""

    model_config = ConfigDict(extra="forbid")

    seed: int
    repeat: int
    control: ProbeRunObservation
    treatment: ProbeRunObservation
    matched_expectation: bool | None
    comparison: str


class NumericAggregate(BaseModel):
    """Aggregate for numeric effect-surface values."""

    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0)
    mean: float | None = None
    std: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    worst: float | None = None


class ParameterProbeResult(BaseModel):
    """Repeated paired verdict for one parameter."""

    model_config = ConfigDict(extra="forbid")

    probe_id: str
    library: str
    model: str
    parameter: str
    expected_surface: EffectSurface
    expected_relation: ExpectedRelation
    outcome: EffectOutcome
    supported: bool
    support_reason: str | None = None
    pairs_total: int = Field(ge=0)
    pairs_eligible: int = Field(ge=0)
    pairs_matched: int = Field(ge=0)
    pairs_failed: int = Field(ge=0)
    matched_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    control_aggregate: NumericAggregate | None = None
    treatment_aggregate: NumericAggregate | None = None
    paired: list[PairedProbeObservation] = Field(default_factory=list)
    holdout_evaluated: bool = False
    prospective_evaluated: bool = False

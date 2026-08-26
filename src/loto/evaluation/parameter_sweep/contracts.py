"""Contracts for the single-game parameter-sweep discovery lane."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ParameterCategory(StrEnum):
    """Scientific role of a constructor or runtime argument."""

    IDENTITY_CONFIGURATION = "identity_configuration"
    TUNABLE_HYPERPARAMETER = "tunable_hyperparameter"
    DATA_DEPENDENT = "data_dependent"
    RUNTIME_RESOURCE = "runtime_resource"
    OUTPUT_CONTROL = "output_control"
    UNSUPPORTED_OR_UNSAFE = "unsupported_or_unsafe"


class SearchSpaceStatus(StrEnum):
    """Whether a model has an approved bounded search space."""

    READY = "READY"
    NO_TUNABLE_PARAMETERS = "NO_TUNABLE_PARAMETERS"
    UNRESOLVED_PARAMETER = "UNRESOLVED_PARAMETER"
    NON_STANDALONE_METHOD = "NON_STANDALONE_METHOD"
    EXPECTED_NEGATIVE_CONTROL = "EXPECTED_NEGATIVE_CONTROL"
    NOT_ROUTABLE = "NOT_ROUTABLE"


class FailureCategory(StrEnum):
    """Fail-visible trial taxonomy."""

    CONSTRUCTOR_ERROR = "CONSTRUCTOR_ERROR"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    DATA_PRECONDITION = "DATA_PRECONDITION"
    FIT_FAILED = "FIT_FAILED"
    PREDICT_FAILED = "PREDICT_FAILED"
    NONFINITE_OUTPUT = "NONFINITE_OUTPUT"
    OUTPUT_SHAPE_INVALID = "OUTPUT_SHAPE_INVALID"
    TIMEOUT = "TIMEOUT"
    OOM = "OOM"
    CUDA_ERROR = "CUDA_ERROR"
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"
    UNKNOWN = "UNKNOWN"


class ParameterDescriptor(BaseModel):
    """Observed constructor parameter with provenance and search classification."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    annotation: str | None = None
    required: bool
    default_repr: str | None = None
    category: ParameterCategory
    tunable: bool
    provenance: tuple[str, ...] = ()
    reason: str = ""


class SearchDimension(BaseModel):
    """One bounded, auditable hyperparameter dimension."""

    model_config = ConfigDict(extra="forbid")

    parameter: str = Field(min_length=1)
    values: tuple[Any, ...] = Field(min_length=2)
    rationale: str = Field(min_length=1)
    provenance: tuple[str, ...] = Field(min_length=1)
    stage: str = "coarse"

    @model_validator(mode="after")
    def validate_values(self) -> SearchDimension:
        if len({repr(item) for item in self.values}) != len(self.values):
            raise ValueError("search-space values must be unique")
        return self


class ModelInventoryRow(BaseModel):
    """One canonical identity in the Bingo5 pilot universe."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    source: str
    library: str
    class_name: str | None = None
    family: str | None = None
    task: str
    provider: str
    adapter: str
    runtime: str
    package: str | None = None
    installed_version: str | None = None
    constructor_signature: str | None = None
    required_args: tuple[str, ...] = ()
    optional_args: tuple[str, ...] = ()
    current_default_params: dict[str, Any] = Field(default_factory=dict)
    certification_params: dict[str, Any] = Field(default_factory=dict)
    upstream_defaults: dict[str, str] = Field(default_factory=dict)
    supports_univariate: bool | None = None
    supports_exog: bool | None = None
    supports_probabilistic: bool | None = None
    supports_gpu: bool | None = None
    supports_cpu: bool | None = None
    supports_bingo5: bool | None = None
    reason_if_not_supported: str | None = None
    parameter_inventory: tuple[ParameterDescriptor, ...] = ()


class ModelSearchSpace(BaseModel):
    """Approved search-space declaration for one canonical identity."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    status: SearchSpaceStatus
    baseline_params: dict[str, Any] = Field(default_factory=dict)
    dimensions: tuple[SearchDimension, ...] = ()
    unresolved_parameters: tuple[str, ...] = ()
    trial_budget: int = Field(default=0, ge=0)
    reason: str = ""

    @model_validator(mode="after")
    def validate_ready_space(self) -> ModelSearchSpace:
        if self.status is SearchSpaceStatus.READY and not self.dimensions:
            raise ValueError("READY search spaces require at least one dimension")
        if self.status is not SearchSpaceStatus.READY and self.trial_budget != 0:
            raise ValueError("non-READY search spaces must have trial_budget=0")
        return self


class PilotRunConfig(BaseModel):
    """Immutable high-level contract for the Bingo5 discovery campaign."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "bingo5-parameter-sweep-v1"
    target_game: str = "bingo5"
    base_commit: str
    run_id: str
    run_root: str
    screening_seed: int = 42
    confirmation_seeds: tuple[int, ...] = (42, 1729, 20260730)
    confirmation_folds: int = 5
    primary_metric: str = "hit_at_1"
    required_metrics: tuple[str, ...] = (
        "hit_at_1",
        "position_hit_at_1",
        "all_positions_hit_at_1",
        "mae",
        "mse",
        "rmse",
    )
    holdout: str = "CLOSED"
    prospective: str = "CLOSED"
    promotion: str = "CLOSED"
    prediction_lock_order: tuple[str, ...] = (
        "prediction_persist",
        "sha256",
        "timestamp",
        "actual_read",
        "score",
    )
    expected_model_identities: int = 250

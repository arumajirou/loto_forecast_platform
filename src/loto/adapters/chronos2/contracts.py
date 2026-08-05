from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Operation(StrEnum):
    IDENTITY = "identity"
    PREDICT = "predict"
    REFERENCE_RELOAD = "reference_reload"


class SeriesLayout(StrEnum):
    POSITION_LOCAL = "position_local"
    POSITION_PANEL = "position_panel"
    POSITION_MULTIVARIATE = "position_multivariate"


class DeviceRequest(StrEnum):
    CPU = "cpu"
    CUDA = "cuda"


class DTypeRequest(StrEnum):
    FLOAT32 = "float32"
    BFLOAT16 = "bfloat16"


class AttentionImplementation(StrEnum):
    SDPA = "sdpa"
    EAGER = "eager"


class ArgumentStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    TRANSFORMED = "TRANSFORMED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNSUPPORTED_BY_VERSION = "UNSUPPORTED_BY_VERSION"
    REJECTED = "REJECTED"
    RUNTIME_VERIFIED = "RUNTIME_VERIFIED"


class PositionRange(StrictModel):
    minimum: int
    maximum: int

    @model_validator(mode="after")
    def validate_range(self) -> PositionRange:
        if self.maximum < self.minimum:
            raise ValueError("position range maximum must be >= minimum")
        return self


class GameGeometry(StrictModel):
    game_id: str = Field(min_length=1, max_length=64)
    position_count: int = Field(gt=0, le=64)
    candidate_min: int
    candidate_max: int
    allow_duplicates: bool = False
    sort_policy: Literal["preserve", "ascending"] = "ascending"
    position_ranges: dict[str, PositionRange] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_domain(self) -> GameGeometry:
        if self.candidate_max < self.candidate_min:
            raise ValueError("candidate_max must be >= candidate_min")
        if self.position_ranges and len(self.position_ranges) != self.position_count:
            raise ValueError("position_ranges must cover every position when provided")
        for name, value_range in self.position_ranges.items():
            if value_range.minimum < self.candidate_min:
                raise ValueError(f"position range {name!r} is below candidate_min")
            if value_range.maximum > self.candidate_max:
                raise ValueError(f"position range {name!r} is above candidate_max")
        return self


class ArgumentLedgerEntry(StrictModel):
    argument: str
    requested_value: Any = None
    effective_value: Any = None
    status: ArgumentStatus
    reason: str | None = None


class PredictionIndexEntry(StrictModel):
    series_id: str
    target_name: str
    horizon_step: int = Field(gt=0)
    timestamp: str


class RuntimeEvidence(StrictModel):
    parent_pid: int | None = Field(default=None, gt=0)
    provider_pid: int = Field(gt=0)
    package_version: str
    requested_device: DeviceRequest
    model_parameter_device: str
    input_device: str = "cpu_dataframe"
    output_device: str = "cpu"
    dtype: DTypeRequest
    attention_implementation: AttentionImplementation
    cpu_preprocessing: bool = True
    cpu_fallback: bool
    finite: bool
    shape_verified: bool
    quantile_monotonicity_verified: bool
    vram_before_bytes: int | None = Field(default=None, ge=0)
    vram_peak_bytes: int | None = Field(default=None, ge=0)
    vram_after_bytes: int | None = Field(default=None, ge=0)
    gpu_uuid: str | None = None
    nvidia_smi_process_match: bool | None = None
    reload_process_distinct: bool | None = None


class GPUProcessEvidence(StrictModel):
    gpu_uuid: str | None = None
    pid: int | None = Field(default=None, gt=0)
    process_match: bool | None = None
    vram_before_bytes: int | None = Field(default=None, ge=0)
    vram_peak_bytes: int | None = Field(default=None, ge=0)
    vram_after_bytes: int | None = Field(default=None, ge=0)


class Chronos2RequestV2(StrictModel):
    schema_version: Literal[2] = 2
    run_id: str
    operation: Operation = Operation.PREDICT
    model_id: Literal["chronos-2"] = "chronos-2"
    repo_id: Literal["amazon/chronos-2"] = "amazon/chronos-2"
    revision: str
    game_geometry: GameGeometry
    series_layout: SeriesLayout
    position_columns: tuple[str, ...] = Field(min_length=1)
    history: tuple[dict[str, Any], ...] = ()
    past_covariates: tuple[dict[str, Any], ...] = ()
    future_covariates: tuple[dict[str, Any], ...] = ()
    context_length: int = Field(default=512, gt=0, le=8192)
    prediction_length: int = Field(default=1, gt=0, le=1024)
    quantile_levels: tuple[float, ...] = (0.1, 0.5, 0.9)
    cross_learning: bool = False
    batch_size: int = Field(default=7, gt=0)
    device: DeviceRequest = DeviceRequest.CUDA
    dtype: DTypeRequest = DTypeRequest.FLOAT32
    attention_implementation: AttentionImplementation = AttentionImplementation.SDPA
    seed: int = 1
    local_files_only: Literal[True] = True
    snapshot_path: str | None = None
    artifact_dir: str | None = None
    reference_manifest_path: str | None = None
    parent_pid: int | None = Field(default=None, gt=0)

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        if not _SAFE_RUN_ID.fullmatch(value):
            raise ValueError("run_id contains unsafe characters")
        return value

    @field_validator("revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        if not _HEX40.fullmatch(value):
            raise ValueError("revision must be a lowercase 40-character hexadecimal commit")
        return value

    @field_validator("position_columns")
    @classmethod
    def validate_position_columns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("position_columns must be unique")
        if any(not name or not name.replace("_", "a").isalnum() for name in value):
            raise ValueError("position_columns contain an invalid identifier")
        return value

    @field_validator("quantile_levels")
    @classmethod
    def validate_quantiles(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if not value:
            raise ValueError("quantile_levels must not be empty")
        if len(set(value)) != len(value):
            raise ValueError("quantile_levels must be unique")
        if any(level <= 0.0 or level >= 1.0 for level in value):
            raise ValueError("quantile_levels must be strictly between 0 and 1")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def validate_contract(self) -> Chronos2RequestV2:
        if len(self.position_columns) != self.game_geometry.position_count:
            raise ValueError("position_columns length must equal game_geometry.position_count")
        if self.game_geometry.position_ranges:
            if set(self.game_geometry.position_ranges) != set(self.position_columns):
                raise ValueError("position_ranges keys must exactly match position_columns")
        if self.operation is not Operation.IDENTITY and len(self.history) < 2:
            raise ValueError("predict operations require at least two history rows")
        if self.past_covariates and len(self.past_covariates) != len(self.history):
            raise ValueError("past_covariates length must equal history length")
        if self.future_covariates and len(self.future_covariates) != self.prediction_length:
            raise ValueError("future_covariates length must equal prediction_length")
        if self.series_layout is SeriesLayout.POSITION_LOCAL and self.cross_learning:
            raise ValueError("position_local requires cross_learning=false")
        if self.series_layout is SeriesLayout.POSITION_PANEL and not self.cross_learning:
            raise ValueError("position_panel requires cross_learning=true")
        if self.series_layout is SeriesLayout.POSITION_MULTIVARIATE and self.cross_learning:
            raise ValueError("position_multivariate requires cross_learning=false in provider v2")
        if self.operation is Operation.REFERENCE_RELOAD and not self.reference_manifest_path:
            raise ValueError("reference_reload requires reference_manifest_path")

        reserved_covariate_names = {
            "item_id",
            "timestamp",
            "target",
            "draw_no",
            "draw_date",
            *self.position_columns,
        }
        past_schema = self._validate_covariate_schema(
            "past_covariates",
            self.past_covariates,
            reserved_covariate_names,
        )
        future_schema = self._validate_covariate_schema(
            "future_covariates",
            self.future_covariates,
            reserved_covariate_names,
        )
        if future_schema and not past_schema:
            raise ValueError("future_covariates require matching past_covariates")
        if not future_schema.issubset(past_schema):
            missing = sorted(future_schema - past_schema)
            raise ValueError(
                "future_covariates keys must be a subset of past_covariates keys: "
                f"{missing}"
            )
        return self

    @staticmethod
    def _validate_covariate_schema(
        label: str,
        rows: tuple[dict[str, Any], ...],
        reserved_names: set[str],
    ) -> set[str]:
        if not rows:
            return set()
        schema = set(rows[0])
        overlap = sorted(schema & reserved_names)
        if overlap:
            raise ValueError(f"{label} contains reserved keys: {overlap}")
        for index, row in enumerate(rows[1:], start=1):
            row_schema = set(row)
            if row_schema != schema:
                raise ValueError(
                    f"{label} row {index} schema differs from row 0: "
                    f"expected={sorted(schema)}, actual={sorted(row_schema)}"
                )
            overlap = sorted(row_schema & reserved_names)
            if overlap:
                raise ValueError(f"{label} contains reserved keys: {overlap}")
        return schema


Matrix = tuple[tuple[float, ...], ...]


class Chronos2ResponseV2(StrictModel):
    schema_version: Literal[2] = 2
    status: Literal["OK", "ERROR", "PARTIAL"]
    run_id: str
    operation: Operation
    model_identity: dict[str, Any] = Field(default_factory=dict)
    effective_arguments: dict[str, Any] = Field(default_factory=dict)
    argument_ledger: tuple[ArgumentLedgerEntry, ...] = ()
    point_forecast: Matrix = ()
    mean_forecast: Matrix = ()
    median_forecast: Matrix = ()
    quantiles: dict[str, Matrix] = Field(default_factory=dict)
    samples: None = None
    prediction_index: tuple[PredictionIndexEntry, ...] = ()
    series_identity: tuple[str, ...] = ()
    artifact_reference: dict[str, Any] = Field(default_factory=dict)
    runtime_evidence: RuntimeEvidence | None = None
    gpu_evidence: GPUProcessEvidence | None = None
    unsupported_arguments: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    error: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_status(self) -> Chronos2ResponseV2:
        if self.status == "ERROR" and self.error is None:
            raise ValueError("ERROR response requires error details")
        if self.status == "OK" and self.error is not None:
            raise ValueError("OK response must not contain error details")
        return self

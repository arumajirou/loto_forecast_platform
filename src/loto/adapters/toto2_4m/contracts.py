from __future__ import annotations

import math
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    field_validator,
    model_validator,
)

from loto.toto2_campaign.model_manifest import (
    MODEL_ID,
    MODEL_LICENSE,
    MODEL_REVISION,
    NATIVE_QUANTILE_LEVELS,
    REPO_ID,
    SOURCE_REVISION,
)

NumericScalar = StrictFloat | StrictInt


class Operation(str, Enum):
    IDENTITY = "identity"
    PREDICT = "predict"


class TimeSemantics(str, Enum):
    DRAW_SEQUENCE = "draw_sequence"
    CALENDAR_TIME = "calendar_time"


class SeriesLayout(str, Enum):
    POSITION_UNIVARIATE = "position_univariate"
    POSITION_MULTIVARIATE = "position_multivariate"


class GameGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    position_count: StrictInt = Field(ge=1, le=64)
    candidate_min: StrictInt
    candidate_max: StrictInt
    strictly_increasing: bool

    @model_validator(mode="after")
    def validate_domain(self) -> GameGeometry:
        if self.candidate_min >= self.candidate_max:
            raise ValueError("candidate_min must be smaller than candidate_max")
        domain_size = self.candidate_max - self.candidate_min + 1
        if self.strictly_increasing and self.position_count > domain_size:
            raise ValueError("strict geometry has more positions than candidate values")
        return self


class Toto2ProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: Literal[2] = 2
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    operation: Operation = Operation.PREDICT
    model_id: Literal[MODEL_ID] = MODEL_ID
    repo_id: Literal[REPO_ID] = REPO_ID
    revision: Literal[MODEL_REVISION] = MODEL_REVISION
    source_revision: Literal[SOURCE_REVISION] = SOURCE_REVISION
    model_license: Literal[MODEL_LICENSE] = MODEL_LICENSE
    game_geometry: GameGeometry
    series_layout: SeriesLayout
    position_columns: list[str] = Field(min_length=1, max_length=64)
    history: list[dict[str, NumericScalar]] = Field(default_factory=list)
    timestamps: list[datetime | StrictInt] = Field(default_factory=list)
    time_semantics: TimeSemantics = TimeSemantics.DRAW_SEQUENCE
    context_length: StrictInt = Field(default=512, ge=1, le=512)
    prediction_length: Literal[1, 2, 5] = 1
    native_quantile_levels: tuple[float, ...] = NATIVE_QUANTILE_LEVELS
    point_method: Literal["median_q0.5"] = "median_q0.5"
    batch_size: Literal[1] = 1
    decode_block_size: StrictInt = Field(default=32, ge=1, le=512)
    device: Literal["cpu", "cuda"] = "cpu"
    dtype: Literal["float32"] = "float32"
    seed: StrictInt = Field(default=1, ge=0, le=2_147_483_647)
    local_files_only: Literal[True] = True
    snapshot_path: str | None = None

    @field_validator("position_columns")
    @classmethod
    def validate_position_columns(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("position_columns must be unique")
        for name in value:
            if not name or not name.replace("_", "").isalnum():
                raise ValueError(f"unsafe position column: {name!r}")
        return value

    @field_validator("native_quantile_levels")
    @classmethod
    def validate_native_quantiles(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        normalized = tuple(round(float(level), 10) for level in value)
        if normalized != NATIVE_QUANTILE_LEVELS:
            raise ValueError("native_quantile_levels must exactly match q0.1 through q0.9")
        return normalized

    @model_validator(mode="after")
    def validate_payload(self) -> Toto2ProviderRequest:
        if len(self.position_columns) != self.game_geometry.position_count:
            raise ValueError("position_columns must match game_geometry.position_count")
        if self.series_layout is SeriesLayout.POSITION_UNIVARIATE:
            if self.game_geometry.position_count != 1:
                raise ValueError("position_univariate requires exactly one position")
        if self.operation is Operation.IDENTITY:
            return self
        if len(self.history) < self.context_length:
            raise ValueError("history must contain at least context_length rows")
        expected_columns = set(self.position_columns)
        for row_index, row in enumerate(self.history):
            if set(row) != expected_columns:
                raise ValueError(f"history row {row_index} columns differ from position_columns")
            for name, value in row.items():
                numeric = float(value)
                if not math.isfinite(numeric):
                    raise ValueError(f"history contains non-finite value: {name}")
        if self.timestamps and len(self.timestamps) != len(self.history):
            raise ValueError("timestamps must be empty or match history length")
        if self.timestamps:
            if self.time_semantics is TimeSemantics.DRAW_SEQUENCE:
                if any(not isinstance(value, int) for value in self.timestamps):
                    raise ValueError("draw_sequence timestamps must be integers")
                draws = [int(value) for value in self.timestamps]
                expected = list(range(draws[0], draws[0] + len(draws)))
                if draws != expected:
                    raise ValueError("draw_sequence timestamps must be increasing and gap-free")
            elif any(not isinstance(value, datetime) for value in self.timestamps):
                raise ValueError("calendar_time timestamps must be datetimes")
            elif any(
                current <= previous
                for previous, current in zip(self.timestamps, self.timestamps[1:], strict=False)
            ):
                raise ValueError("calendar_time timestamps must be strictly increasing")
        return self


class RuntimeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_pid: StrictInt = Field(gt=0)
    requested_device: Literal["cpu", "cuda"]
    execution_device: str
    model_device: str
    output_device: str
    peak_vram_bytes: StrictInt = Field(ge=0)
    external_gpu_pid_captured: bool
    cpu_fallback: bool
    runtime_scope: Literal["FULL_INFERENCE", "CONTRACT_ONLY"]


class Toto2ProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: Literal[2] = 2
    status: Literal["OK", "ERROR", "BLOCKED"]
    phase: str
    message: str
    model_identity: dict[str, Any] = Field(default_factory=dict)
    effective_arguments: dict[str, Any] = Field(default_factory=dict)
    point_forecast: list[list[float]] = Field(default_factory=list)
    point_method: Literal["median_q0.5"] = "median_q0.5"
    quantiles: dict[str, list[list[float]]] = Field(default_factory=dict)
    series_identity: list[str] = Field(default_factory=list)
    prediction_index: list[int] = Field(default_factory=list)
    runtime_evidence: RuntimeEvidence | None = None
    artifact_reference: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    unsupported_arguments: list[str] = Field(default_factory=list)

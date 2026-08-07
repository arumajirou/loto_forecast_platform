from __future__ import annotations

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

from loto.moirai2_campaign.model_manifest import (
    MODEL_ID,
    MODEL_REVISION,
    NATIVE_QUANTILE_LEVELS,
    REPO_ID,
)


NumericScalar = StrictFloat | StrictInt


class Operation(str, Enum):
    IDENTITY = "identity"
    PREDICT = "predict"


class TimeSemantics(str, Enum):
    DRAW_SEQUENCE = "draw_sequence"
    CALENDAR_TIME = "calendar_time"


class GameGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    position_count: StrictInt = Field(ge=1, le=64)
    candidate_min: StrictInt
    candidate_max: StrictInt
    strictly_increasing: bool

    @model_validator(mode="after")
    def validate_domain(self) -> "GameGeometry":
        if self.candidate_min >= self.candidate_max:
            raise ValueError("candidate_min must be smaller than candidate_max")
        domain_size = self.candidate_max - self.candidate_min + 1
        if self.strictly_increasing and self.position_count > domain_size:
            raise ValueError("strict geometry has more positions than available candidates")
        return self


class Moirai2ProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: Literal[2] = 2
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    operation: Operation = Operation.PREDICT
    model_id: Literal[MODEL_ID] = MODEL_ID
    repo_id: Literal[REPO_ID] = REPO_ID
    revision: Literal[MODEL_REVISION] = MODEL_REVISION
    license_lane: Literal["personal_noncommercial_research"]
    game_geometry: GameGeometry
    series_layout: Literal["position_multivariate", "position_univariate"]
    position_columns: list[str] = Field(min_length=1, max_length=64)
    history: list[dict[str, NumericScalar]] = Field(default_factory=list)
    timestamps: list[datetime | StrictInt] = Field(default_factory=list)
    time_semantics: TimeSemantics = TimeSemantics.DRAW_SEQUENCE
    past_covariates: dict[str, list[NumericScalar]] = Field(default_factory=dict)
    future_covariates: dict[str, list[NumericScalar]] = Field(default_factory=dict)
    future_covariate_availability: dict[
        str, Literal["known_at_prediction_time"]
    ] = Field(default_factory=dict)
    context_length: StrictInt = Field(default=128, ge=1)
    prediction_length: Literal[1, 2, 5] = 1
    native_quantile_levels: tuple[float, ...] = NATIVE_QUANTILE_LEVELS
    point_method: Literal["median_q0.5"] = "median_q0.5"
    batch_size: StrictInt = Field(default=1, ge=1, le=1024)
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

    @field_validator(
        "past_covariates",
        "future_covariates",
        "future_covariate_availability",
    )
    @classmethod
    def validate_covariate_names(cls, value: dict[str, Any]) -> dict[str, Any]:
        for name in value:
            if not name or not name.replace("_", "").isalnum():
                raise ValueError(f"unsafe covariate name: {name!r}")
        return value

    @field_validator("native_quantile_levels")
    @classmethod
    def validate_native_quantiles(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        normalized = tuple(round(float(level), 10) for level in value)
        if normalized != NATIVE_QUANTILE_LEVELS:
            raise ValueError("native_quantile_levels must exactly match the model configuration")
        return normalized

    @model_validator(mode="after")
    def validate_payload(self) -> "Moirai2ProviderRequest":
        if len(self.position_columns) != self.game_geometry.position_count:
            raise ValueError("position_columns must match game_geometry.position_count")
        if self.series_layout == "position_univariate" and len(self.position_columns) != 1:
            raise ValueError("position_univariate requires exactly one position column")
        if self.operation is Operation.IDENTITY:
            return self
        if not self.history:
            raise ValueError("history is required for predict")
        if len(self.history) < self.context_length:
            raise ValueError("history must contain at least context_length rows")
        expected_columns = set(self.position_columns)
        for index, row in enumerate(self.history):
            if set(row) != expected_columns:
                raise ValueError(
                    f"history row {index} columns differ from position_columns"
                )
        if self.timestamps and len(self.timestamps) != len(self.history):
            raise ValueError("timestamps must be empty or match history length")
        if self.timestamps:
            if self.time_semantics is TimeSemantics.DRAW_SEQUENCE:
                if any(not isinstance(value, int) for value in self.timestamps):
                    raise ValueError("draw_sequence timestamps must be integer draw numbers")
                draws = [int(value) for value in self.timestamps]
                expected_draws = list(range(draws[0], draws[0] + len(draws)))
                if draws != expected_draws:
                    raise ValueError(
                        "draw_sequence timestamps must be unique, increasing, and gap-free"
                    )
            elif any(not isinstance(value, datetime) for value in self.timestamps):
                raise ValueError("calendar_time timestamps must be datetimes")
        for name, values in self.past_covariates.items():
            if len(values) != len(self.history):
                raise ValueError(
                    f"past covariate {name!r} must contain exactly history length values"
                )
        expected_known_future = len(self.history) + self.prediction_length
        if set(self.future_covariates) != set(self.future_covariate_availability):
            raise ValueError(
                "future covariates require matching known-at-prediction-time evidence"
            )
        for name, values in self.future_covariates.items():
            if len(values) != expected_known_future:
                raise ValueError(
                    f"future covariate {name!r} must contain history+horizon values"
                )
        from loto.moirai2_campaign.token_geometry import calculate_token_geometry

        calculate_token_geometry(
            target_dim=self.game_geometry.position_count,
            context_length=self.context_length,
            prediction_length=self.prediction_length,
        )
        return self


class RuntimeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    process_id: int
    package_version: str
    runtime_lane: str
    requested_device: str
    execution_device: str
    model_parameter_device: str
    output_shape: list[int]
    all_quantiles_finite: bool
    quantile_monotonicity: bool
    cpu_fallback: bool


class GpuEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_device: str
    execution_device: str
    cuda_available: bool
    provider_pid: int
    gpu_pid: int | None
    peak_vram_bytes: int
    cpu_fallback: bool


class LicenseEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code_license: Literal["Apache-2.0"]
    model_license: Literal["CC-BY-NC-4.0"]
    license_lane: Literal["personal_noncommercial_research"]
    research_only: Literal[True]
    production_champion_eligible: Literal[False]
    automatic_promotion: Literal[False]
    commercial_deployment_certified: Literal[False]


class Moirai2ProviderResponse(BaseModel):
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
    samples: None = None
    series_identity: list[str] = Field(default_factory=list)
    prediction_index: list[int] = Field(default_factory=list)
    runtime_evidence: RuntimeEvidence | None = None
    gpu_evidence: GpuEvidence | None = None
    artifact_reference: dict[str, Any] = Field(default_factory=dict)
    license_evidence: LicenseEvidence | None = None
    warnings: list[str] = Field(default_factory=list)
    unsupported_arguments: list[str] = Field(default_factory=list)


def request_v1_to_v2(
    request: dict[str, Any],
    *,
    run_id: str = "schema-v1-compat",
) -> dict[str, Any]:
    """Convert the legacy Loto7-only request into the isolated v2 contract."""
    if int(request.get("schema_version", 0)) != 1:
        raise ValueError("request_v1_to_v2 accepts only schema_version=1")
    allowed = {
        "schema_version",
        "model_id",
        "repo_id",
        "revision",
        "local_files_only",
        "device",
        "dtype",
        "history",
        "prediction_length",
        "snapshot_path",
    }
    unknown = sorted(set(request) - allowed)
    if unknown:
        raise ValueError(f"legacy request has unknown keys: {unknown}")
    history = request.get("history")
    if not isinstance(history, list) or not history:
        raise ValueError("legacy history must be a non-empty list")
    position_columns = [f"n{position}" for position in range(1, 8)]
    for index, row in enumerate(history):
        if not isinstance(row, dict) or set(row) != set(position_columns):
            raise ValueError(f"legacy history row {index} is not the exact Loto7 layout")
    prediction_length = int(request.get("prediction_length", 1))
    if prediction_length not in {1, 2, 5}:
        raise ValueError("legacy prediction_length is outside formal v2 horizons")
    context_length = min(128, len(history))
    payload = {
        "schema_version": 2,
        "run_id": run_id,
        "operation": "predict",
        "model_id": MODEL_ID,
        "repo_id": REPO_ID,
        "revision": MODEL_REVISION,
        "license_lane": "personal_noncommercial_research",
        "game_geometry": {
            "game_id": "loto7",
            "position_count": 7,
            "candidate_min": 1,
            "candidate_max": 37,
            "strictly_increasing": True,
        },
        "series_layout": "position_multivariate",
        "position_columns": position_columns,
        "history": history,
        "timestamps": [],
        "time_semantics": "draw_sequence",
        "past_covariates": {},
        "future_covariates": {},
        "future_covariate_availability": {},
        "context_length": context_length,
        "prediction_length": prediction_length,
        "native_quantile_levels": list(NATIVE_QUANTILE_LEVELS),
        "point_method": "median_q0.5",
        "batch_size": 1,
        "device": request.get("device", "cpu"),
        "dtype": "float32",
        "seed": 1,
        "local_files_only": True,
        "snapshot_path": request.get("snapshot_path"),
    }
    return Moirai2ProviderRequest.model_validate(payload).model_dump(mode="json")

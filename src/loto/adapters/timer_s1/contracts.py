from __future__ import annotations

import math
import re
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MODEL_ID = "timer-s1"
CANONICAL_REPO = "bytedance-research/Timer-S1"
MIRROR_REPO = "thuml/Timer-S1"
UNPINNED = "UNPINNED"
QUANTILE_LEVELS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
QUANTILE_KEYS = tuple(f"q{level:.1f}" for level in QUANTILE_LEVELS)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Operation(StrEnum):
    IDENTITY = "identity"
    PREDICT = "predict"


class Game(StrEnum):
    NUMBERS3 = "numbers3"
    NUMBERS4 = "numbers4"
    MINILOTO = "miniloto"
    LOTO6 = "loto6"
    LOTO7 = "loto7"


class TimelineMode(StrEnum):
    DRAW_SEQUENCE = "draw-sequence"
    CALENDAR_TIME = "calendar-time"


class RequestedDevice(StrEnum):
    CPU = "cpu"
    CUDA = "cuda"


class TargetLayout(StrEnum):
    POSITION_UNIVARIATE = "position_univariate"


class BatchSemantics(StrEnum):
    INDEPENDENT_SERIES = "independent_series"


class ProviderStatus(StrEnum):
    EXECUTION_PENDING = "EXECUTION_PENDING"
    VERIFIED_CPU = "VERIFIED_CPU"
    VERIFIED_GPU = "VERIFIED_GPU"
    FAILED = "FAILED"


class HistoryRow(StrictModel):
    timestamp: datetime
    values: tuple[float, ...] = Field(min_length=1)
    future_actual: Literal[False] = False

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        raise ValueError("timestamp must be an ISO-8601 datetime")

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value

    @field_validator("values", mode="before")
    @classmethod
    def parse_values(cls, value: object) -> tuple[float, ...]:
        if isinstance(value, tuple):
            return value
        if isinstance(value, list):
            return tuple(value)
        raise ValueError("values must be a JSON array")

    @field_validator("values")
    @classmethod
    def validate_values(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if any(not math.isfinite(item) for item in value):
            raise ValueError("history values must be finite")
        return value


class ChronologyEvidence(StrictModel):
    row_count: int = Field(ge=0)
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    strictly_increasing: bool
    duplicate_timestamps: int = Field(ge=0)
    future_actuals_used: Literal[False] = False
    calendar_mapping_sha256: str

    @field_validator("calendar_mapping_sha256")
    @classmethod
    def validate_mapping_sha(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("calendar_mapping_sha256 must be lowercase SHA-256")
        return value


class TimerS1Request(StrictModel):
    schema_version: Literal[1] = 1
    run_id: str
    operation: Operation = Operation.PREDICT
    model_id: Literal[MODEL_ID] = MODEL_ID
    model_repo: Literal[CANONICAL_REPO] = CANONICAL_REPO
    package_version: str
    source_revision: str
    model_revision: str
    config_sha256: str
    weight_sha256: str
    weight_manifest_sha256: str
    license: Literal["Apache-2.0"] = "Apache-2.0"
    game: Game
    target_layout: Literal[TargetLayout.POSITION_UNIVARIATE] = (
        TargetLayout.POSITION_UNIVARIATE
    )
    batch_semantics: Literal[BatchSemantics.INDEPENDENT_SERIES] = (
        BatchSemantics.INDEPENDENT_SERIES
    )
    joint_multivariate: Literal[False] = False
    timeline_mode: TimelineMode
    context_length: int = Field(gt=0, le=11_520)
    prediction_length: Literal[1, 2, 5]
    seed: int = 1
    requested_device: RequestedDevice
    history: tuple[HistoryRow, ...] = ()
    past_covariates: None = None
    known_future_covariates: None = None
    snapshot_path: str | None = None
    manifest_path: str | None = None
    remote_code_review_path: str | None = None

    @field_validator("operation", mode="before")
    @classmethod
    def parse_operation(cls, value: object) -> Operation:
        return value if isinstance(value, Operation) else Operation(value)

    @field_validator("game", mode="before")
    @classmethod
    def parse_game(cls, value: object) -> Game:
        return value if isinstance(value, Game) else Game(value)

    @field_validator("timeline_mode", mode="before")
    @classmethod
    def parse_timeline_mode(cls, value: object) -> TimelineMode:
        return value if isinstance(value, TimelineMode) else TimelineMode(value)

    @field_validator("requested_device", mode="before")
    @classmethod
    def parse_requested_device(cls, value: object) -> RequestedDevice:
        return value if isinstance(value, RequestedDevice) else RequestedDevice(value)

    @field_validator("target_layout", mode="before")
    @classmethod
    def parse_target_layout(cls, value: object) -> TargetLayout:
        return value if isinstance(value, TargetLayout) else TargetLayout(value)

    @field_validator("batch_semantics", mode="before")
    @classmethod
    def parse_batch_semantics(cls, value: object) -> BatchSemantics:
        return value if isinstance(value, BatchSemantics) else BatchSemantics(value)

    @field_validator("history", mode="before")
    @classmethod
    def parse_history(cls, value: object) -> tuple[object, ...]:
        if isinstance(value, tuple):
            return value
        if isinstance(value, list):
            return tuple(value)
        raise ValueError("history must be a JSON array")

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        if not _RUN_ID.fullmatch(value):
            raise ValueError("run_id contains unsafe characters")
        return value

    @field_validator("source_revision", "model_revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        if value != UNPINNED and not _REVISION.fullmatch(value):
            raise ValueError("revision must be UNPINNED or a lowercase 40-character SHA")
        return value

    @field_validator("config_sha256", "weight_sha256", "weight_manifest_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if value != UNPINNED and not _SHA256.fullmatch(value):
            raise ValueError("artifact hash must be UNPINNED or lowercase SHA-256")
        return value

    @model_validator(mode="after")
    def validate_operation(self) -> TimerS1Request:
        if self.operation is Operation.PREDICT:
            if len(self.history) < 2:
                raise ValueError("predict requires at least two history rows")
            if len(self.history) < self.context_length:
                raise ValueError("history rows must cover context_length")
        return self


class TimerS1Response(StrictModel):
    schema_version: Literal[1] = 1
    run_id: str
    status: ProviderStatus
    runtime_verified: Literal[True] = True
    model_id: Literal[MODEL_ID] = MODEL_ID
    model_repo: Literal[CANONICAL_REPO] = CANONICAL_REPO
    package_version: str
    source_revision: str
    model_revision: str
    config_sha256: str
    weight_sha256: str
    weight_manifest_sha256: str
    license: Literal["Apache-2.0"] = "Apache-2.0"
    game: Game
    target_layout: Literal[TargetLayout.POSITION_UNIVARIATE]
    timeline_mode: TimelineMode
    context_length: int = Field(gt=0, le=11_520)
    prediction_length: Literal[1, 2, 5]
    seed: int
    requested_device: RequestedDevice
    effective_device: str
    cpu_fallback: bool
    input_shape: tuple[int, int]
    native_output_shape: tuple[int, int, int]
    output_shape: tuple[int, int]
    point_forecast: tuple[tuple[float, ...], ...]
    quantiles: dict[str, tuple[tuple[float, ...], ...]]
    samples: None = None
    finite_check: Literal[True] = True
    quantile_monotonicity_check: Literal[True] = True
    chronology_evidence: ChronologyEvidence
    actuals_used: Literal[False] = False
    runtime_pid: int = Field(gt=0)
    gpu_uuid: str | None = None
    gpu_process_vram_before_bytes: int | None = Field(default=None, ge=0)
    gpu_process_vram_peak_bytes: int | None = Field(default=None, ge=0)
    gpu_process_vram_after_bytes: int | None = Field(default=None, ge=0)
    artifact_paths: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_runtime_response(self) -> TimerS1Response:
        if tuple(self.quantiles) != QUANTILE_KEYS:
            raise ValueError("quantiles must contain q0.1 through q0.9 in order")
        if self.point_forecast != self.quantiles["q0.5"]:
            raise ValueError("point_forecast must equal q0.5")
        if self.native_output_shape[1] != 9:
            raise ValueError("native output must contain exactly nine quantiles")
        if self.native_output_shape[2] != self.prediction_length:
            raise ValueError("native output horizon does not match prediction_length")
        if self.output_shape != (
            self.native_output_shape[0],
            self.native_output_shape[2],
        ):
            raise ValueError("output_shape must be [series, prediction_length]")
        if self.status is ProviderStatus.VERIFIED_GPU:
            if self.requested_device is not RequestedDevice.CUDA:
                raise ValueError("VERIFIED_GPU requires requested_device=cuda")
            if self.cpu_fallback:
                raise ValueError("CPU fallback cannot produce VERIFIED_GPU")
            if not self.gpu_uuid or self.gpu_process_vram_peak_bytes is None:
                raise ValueError("VERIFIED_GPU requires GPU UUID and process VRAM")
        return self


class TimerS1FailureResponse(StrictModel):
    schema_version: Literal[1] = 1
    run_id: str
    status: Literal[ProviderStatus.EXECUTION_PENDING, ProviderStatus.FAILED]
    runtime_verified: Literal[False] = False
    model_id: Literal[MODEL_ID] = MODEL_ID
    model_repo: Literal[CANONICAL_REPO] = CANONICAL_REPO
    error_code: str
    error_message: str
    effective_device: None = None
    cpu_fallback: Literal[False] = False
    actuals_used: Literal[False] = False
    artifact_paths: tuple[str, ...] = ()

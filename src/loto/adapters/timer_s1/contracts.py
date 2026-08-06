from __future__ import annotations

import math
import re
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
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
_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        allow_inf_nan=False,
    )


class Operation(StrEnum):
    IDENTITY = "identity"
    PREDICT = "predict"


class Game(StrEnum):
    NUMBERS3 = "numbers3"
    NUMBERS4 = "numbers4"
    MINILOTO = "miniloto"
    LOTO6 = "loto6"
    LOTO7 = "loto7"


POSITION_COUNTS: dict[Game, int] = {
    Game.NUMBERS3: 3,
    Game.NUMBERS4: 4,
    Game.MINILOTO: 5,
    Game.LOTO6: 6,
    Game.LOTO7: 7,
}


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


def _parse_enum(value: object, enum_type: type[StrEnum]) -> StrEnum:
    return value if isinstance(value, enum_type) else enum_type(value)


def _validate_run_id(value: str) -> str:
    if not _RUN_ID.fullmatch(value):
        raise ValueError("run_id contains unsafe characters")
    return value


def _validate_revision(value: str) -> str:
    if value != UNPINNED and not _REVISION.fullmatch(value):
        raise ValueError("revision must be UNPINNED or a lowercase 40-character SHA")
    return value


def _validate_sha256(value: str) -> str:
    if value != UNPINNED and not _SHA256.fullmatch(value):
        raise ValueError("artifact hash must be UNPINNED or lowercase SHA-256")
    return value


def _validate_artifact_path(value: str) -> str:
    if not value or "\\" in value or "\x00" in value:
        raise ValueError("artifact path must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("artifact path must remain inside the run directory")
    return value


def _validate_matrix(
    name: str,
    matrix: tuple[tuple[float, ...], ...],
    expected_rows: int,
    expected_columns: int,
) -> None:
    if len(matrix) != expected_rows:
        raise ValueError(f"{name} must contain exactly {expected_rows} series")
    for row_index, row in enumerate(matrix):
        if len(row) != expected_columns:
            raise ValueError(
                f"{name} series {row_index} must contain exactly "
                f"{expected_columns} horizon values"
            )
        if any(not math.isfinite(value) for value in row):
            raise ValueError(f"{name} must contain only finite values")


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

    @model_validator(mode="after")
    def validate_consistency(self) -> ChronologyEvidence:
        if self.row_count == 0:
            if self.first_timestamp is not None or self.last_timestamp is not None:
                raise ValueError("empty chronology cannot contain timestamps")
            return self
        if self.first_timestamp is None or self.last_timestamp is None:
            raise ValueError("non-empty chronology requires first and last timestamps")
        for timestamp in (self.first_timestamp, self.last_timestamp):
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("chronology timestamps must include a timezone")
        if self.first_timestamp > self.last_timestamp:
            raise ValueError("chronology timestamps are reversed")
        if self.row_count > 1 and self.first_timestamp == self.last_timestamp:
            raise ValueError("multi-row chronology must span distinct timestamps")
        if self.strictly_increasing and self.duplicate_timestamps != 0:
            raise ValueError("strict chronology cannot report duplicate timestamps")
        return self


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
        return Operation(_parse_enum(value, Operation))

    @field_validator("game", mode="before")
    @classmethod
    def parse_game(cls, value: object) -> Game:
        return Game(_parse_enum(value, Game))

    @field_validator("timeline_mode", mode="before")
    @classmethod
    def parse_timeline_mode(cls, value: object) -> TimelineMode:
        return TimelineMode(_parse_enum(value, TimelineMode))

    @field_validator("requested_device", mode="before")
    @classmethod
    def parse_requested_device(cls, value: object) -> RequestedDevice:
        return RequestedDevice(_parse_enum(value, RequestedDevice))

    @field_validator("target_layout", mode="before")
    @classmethod
    def parse_target_layout(cls, value: object) -> TargetLayout:
        return TargetLayout(_parse_enum(value, TargetLayout))

    @field_validator("batch_semantics", mode="before")
    @classmethod
    def parse_batch_semantics(cls, value: object) -> BatchSemantics:
        return BatchSemantics(_parse_enum(value, BatchSemantics))

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
        return _validate_run_id(value)

    @field_validator("source_revision", "model_revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        return _validate_revision(value)

    @field_validator("config_sha256", "weight_sha256", "weight_manifest_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        return _validate_sha256(value)

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
    status: Literal[ProviderStatus.VERIFIED_CPU, ProviderStatus.VERIFIED_GPU]
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
    cpu_fallback: Literal[False] = False
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

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, value: object) -> ProviderStatus:
        return ProviderStatus(_parse_enum(value, ProviderStatus))

    @field_validator("game", mode="before")
    @classmethod
    def parse_game(cls, value: object) -> Game:
        return Game(_parse_enum(value, Game))

    @field_validator("timeline_mode", mode="before")
    @classmethod
    def parse_timeline_mode(cls, value: object) -> TimelineMode:
        return TimelineMode(_parse_enum(value, TimelineMode))

    @field_validator("requested_device", mode="before")
    @classmethod
    def parse_requested_device(cls, value: object) -> RequestedDevice:
        return RequestedDevice(_parse_enum(value, RequestedDevice))

    @field_validator("target_layout", mode="before")
    @classmethod
    def parse_target_layout(cls, value: object) -> TargetLayout:
        return TargetLayout(_parse_enum(value, TargetLayout))

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        return _validate_run_id(value)

    @field_validator("package_version")
    @classmethod
    def validate_package_version(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or normalized in {"UNVERIFIED", UNPINNED}:
            raise ValueError("verified response package_version must be concrete")
        return normalized

    @field_validator("source_revision", "model_revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        value = _validate_revision(value)
        if value == UNPINNED:
            raise ValueError("verified response revisions must be pinned")
        return value

    @field_validator("config_sha256", "weight_sha256", "weight_manifest_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        value = _validate_sha256(value)
        if value == UNPINNED:
            raise ValueError("verified response artifact hashes must be pinned")
        return value

    @field_validator("artifact_paths")
    @classmethod
    def validate_artifact_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_validate_artifact_path(path) for path in value)

    @model_validator(mode="after")
    def validate_runtime_response(self) -> TimerS1Response:
        expected_series = POSITION_COUNTS[self.game]
        expected_input_shape = (expected_series, self.context_length)
        expected_output_shape = (expected_series, self.prediction_length)
        expected_native_shape = (expected_series, 9, self.prediction_length)
        if self.input_shape != expected_input_shape:
            raise ValueError("input_shape does not match game geometry and context_length")
        if self.native_output_shape != expected_native_shape:
            raise ValueError("native_output_shape must be [game series, 9, prediction_length]")
        if self.output_shape != expected_output_shape:
            raise ValueError("output_shape must be [game series, prediction_length]")
        if set(self.quantiles) != set(QUANTILE_KEYS):
            raise ValueError("quantiles must contain exactly q0.1 through q0.9")
        _validate_matrix(
            "point_forecast",
            self.point_forecast,
            expected_series,
            self.prediction_length,
        )
        for key in QUANTILE_KEYS:
            _validate_matrix(
                key,
                self.quantiles[key],
                expected_series,
                self.prediction_length,
            )
        if self.point_forecast != self.quantiles["q0.5"]:
            raise ValueError("point_forecast must equal q0.5")
        for series_index in range(expected_series):
            for step in range(self.prediction_length):
                ordered = [
                    self.quantiles[key][series_index][step] for key in QUANTILE_KEYS
                ]
                if any(
                    left > right
                    for left, right in zip(ordered, ordered[1:], strict=False)
                ):
                    raise ValueError("quantile values must be monotone at every cell")
        chronology = self.chronology_evidence
        if chronology.row_count != self.context_length:
            raise ValueError("chronology row_count must equal context_length")
        if not chronology.strictly_increasing or chronology.duplicate_timestamps != 0:
            raise ValueError("verified response requires strict duplicate-free chronology")
        if self.status is ProviderStatus.VERIFIED_CPU:
            if self.requested_device is not RequestedDevice.CPU:
                raise ValueError("VERIFIED_CPU requires requested_device=cpu")
            if self.effective_device != "cpu":
                raise ValueError("VERIFIED_CPU requires effective_device=cpu")
            if any(
                value is not None
                for value in (
                    self.gpu_uuid,
                    self.gpu_process_vram_before_bytes,
                    self.gpu_process_vram_peak_bytes,
                    self.gpu_process_vram_after_bytes,
                )
            ):
                raise ValueError("VERIFIED_CPU cannot contain GPU process evidence")
        else:
            if self.requested_device is not RequestedDevice.CUDA:
                raise ValueError("VERIFIED_GPU requires requested_device=cuda")
            if not self.effective_device.startswith("cuda"):
                raise ValueError("VERIFIED_GPU requires an effective CUDA device")
            if not self.gpu_uuid:
                raise ValueError("VERIFIED_GPU requires GPU UUID evidence")
            vram_values = (
                self.gpu_process_vram_before_bytes,
                self.gpu_process_vram_peak_bytes,
                self.gpu_process_vram_after_bytes,
            )
            if any(value is None for value in vram_values):
                raise ValueError("VERIFIED_GPU requires before, peak, and after VRAM evidence")
            before, peak, after = vram_values
            assert before is not None and peak is not None and after is not None
            if peak <= 0 or peak < before or peak < after:
                raise ValueError("GPU peak VRAM evidence is inconsistent")
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

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, value: object) -> ProviderStatus:
        return ProviderStatus(_parse_enum(value, ProviderStatus))

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        return _validate_run_id(value)

    @field_validator("error_code")
    @classmethod
    def validate_error_code(cls, value: str) -> str:
        if not _ERROR_CODE.fullmatch(value):
            raise ValueError("error_code must be an uppercase machine-readable identifier")
        return value

    @field_validator("artifact_paths")
    @classmethod
    def validate_artifact_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_validate_artifact_path(path) for path in value)

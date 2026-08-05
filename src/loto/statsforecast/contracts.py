from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TimeAxisMode(StrEnum):
    DRAW_SEQUENCE = "draw_sequence"
    CALENDAR_TIME = "calendar_time"


class ExpectedStatus(StrEnum):
    EXPECTED_PASS = "EXPECTED_PASS"
    EXPECTED_NEGATIVE_PASS = "EXPECTED_NEGATIVE_PASS"
    EXPECTED_DATA_PRECONDITION = "EXPECTED_DATA_PRECONDITION"
    UNSUPPORTED_BY_VERSION = "UNSUPPORTED_BY_VERSION"
    BLOCKED_OPTIONAL_DEPENDENCY = "BLOCKED_OPTIONAL_DEPENDENCY"
    UNEXPECTED_FAILURE = "UNEXPECTED_FAILURE"


class RuntimeStatus(StrEnum):
    VERIFIED = "VERIFIED"
    EXPECTED_NEGATIVE_PASS = "EXPECTED_NEGATIVE_PASS"
    INVENTORY_MISMATCH = "INVENTORY_MISMATCH"
    DATA_PRECONDITION_FAILED = "DATA_PRECONDITION_FAILED"
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class ArgumentState(StrEnum):
    ACCEPTED = "ACCEPTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNSUPPORTED_BY_VERSION = "UNSUPPORTED_BY_VERSION"
    REJECTED = "REJECTED"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TimeAxisContract(StrictModel):
    mode: TimeAxisMode = TimeAxisMode.DRAW_SEQUENCE
    source_column: str = "draw_no"
    freq: int | str = 1

    @model_validator(mode="after")
    def validate_mode_and_frequency(self) -> TimeAxisContract:
        if self.mode is TimeAxisMode.DRAW_SEQUENCE:
            if self.freq != 1:
                raise ValueError("draw_sequence requires freq=1")
            if self.source_column != "draw_no":
                raise ValueError("draw_sequence requires source_column='draw_no'")
        else:
            if not isinstance(self.freq, str) or not self.freq.strip():
                raise ValueError("calendar_time requires a non-empty string frequency")
            if self.source_column == "draw_no":
                raise ValueError("calendar_time requires a datetime source column")
        return self


class GameGeometry(StrictModel):
    game: str = Field(min_length=1)
    positions: tuple[str, ...]
    candidate_min: int
    candidate_max: int
    top_k: int
    time_axis: TimeAxisContract = Field(default_factory=TimeAxisContract)

    @model_validator(mode="after")
    def validate_geometry(self) -> GameGeometry:
        if not self.positions or len(set(self.positions)) != len(self.positions):
            raise ValueError("positions must be non-empty and unique")
        if self.candidate_min > self.candidate_max:
            raise ValueError("candidate_min must not exceed candidate_max")
        candidate_count = self.candidate_max - self.candidate_min + 1
        if not 1 <= self.top_k <= candidate_count:
            raise ValueError("top_k must fit inside the candidate range")
        return self


class ModelContract(StrictModel):
    name: str
    expected_status: ExpectedStatus = ExpectedStatus.EXPECTED_PASS
    source: Literal["UPSTREAM_EXPORT", "PROJECT_EXTENSION"] = "UPSTREAM_EXPORT"
    champion_eligible: bool = True
    required_parameters: tuple[str, ...] = ()
    requires_explicit_configuration: bool = False
    minimum_seasons: int | None = Field(default=None, ge=1)
    capabilities: tuple[str, ...] = ()
    notes: str = ""


class CampaignConfig(StrictModel):
    geometry: GameGeometry
    model_names: tuple[str, ...]
    horizon: int = Field(default=1, ge=1)
    validation_size: int = Field(default=20, ge=1)
    holdout_size: int = Field(default=20, ge=1)
    seed: int = 1
    seeds: tuple[int, ...] = (1, 7, 19)
    outer_workers: int = Field(default=8, ge=1)
    n_jobs: int = Field(default=1, ge=1)
    levels: tuple[int, ...] = (80, 90)
    model_parameters: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_execution_contract(self) -> CampaignConfig:
        if not self.model_names or len(set(self.model_names)) != len(self.model_names):
            raise ValueError("model_names must be non-empty and unique")
        if self.n_jobs != 1:
            raise ValueError("nested StatsForecast parallelism must remain n_jobs=1")
        if not self.seeds or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("formal seeds must be non-empty and unique")
        if any(level <= 0 or level >= 100 for level in self.levels):
            raise ValueError("prediction interval levels must be between 0 and 100")
        unknown = set(self.model_parameters).difference(self.model_names)
        if unknown:
            raise ValueError(f"model_parameters contain unselected models: {sorted(unknown)}")
        return self

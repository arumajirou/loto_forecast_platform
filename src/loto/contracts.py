"""Versioned logical contracts shared across the platform."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0.0"


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)
    schema_version: str = SCHEMA_VERSION


class DatasetManifest(StrictContract):
    dataset_id: str
    data_version: str
    lottery: str = "loto7"
    row_count: int = Field(ge=0)
    first_draw_no: int | None = None
    last_draw_no: int | None = None
    first_draw_date: datetime | None = None
    last_draw_date: datetime | None = None
    sha256: str = Field(min_length=64, max_length=64)
    source: str = "user-supplied"


class FeatureSetManifest(StrictContract):
    feature_set_id: str
    data_version: str
    row_count: int = Field(ge=0)
    windows: list[int]
    sha256: str = Field(min_length=64, max_length=64)
    leakage_checked: bool = True


class CandidateProbability(StrictContract):
    candidate_number: int = Field(ge=1, le=37)
    probability: float = Field(ge=0.0, le=1.0)
    rank_score: float


class PositionProbability(StrictContract):
    position: int = Field(ge=1, le=7)
    candidate_number: int = Field(ge=1, le=37)
    probability: float = Field(ge=0.0, le=1.0)


class DecodedCombination(StrictContract):
    numbers: list[int] = Field(min_length=7, max_length=7)
    score: float

    @model_validator(mode="after")
    def validate_numbers(self) -> "DecodedCombination":
        if any(n < 1 or n > 37 for n in self.numbers):
            raise ValueError("numbers must be in [1, 37]")
        if any(a >= b for a, b in zip(self.numbers, self.numbers[1:])):
            raise ValueError("numbers must be strictly ascending and unique")
        return self


class ForecastPackage(StrictContract):
    forecast_id: str
    draw_id: str
    model_id: str
    data_version: str
    feature_set_id: str
    created_at: datetime
    draw_time: datetime
    combination: DecodedCombination
    candidates: list[CandidateProbability] = Field(min_length=37, max_length=37)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_forecast(self) -> "ForecastPackage":
        nums = [c.candidate_number for c in self.candidates]
        if sorted(nums) != list(range(1, 38)):
            raise ValueError("candidates must contain every number 1..37 exactly once")
        if self.created_at >= self.draw_time:
            raise ValueError("forecast must be created before draw_time")
        return self


class EvaluationReport(StrictContract):
    report_id: str
    model_id: str
    n_draws: int = Field(ge=0)
    metrics: dict[str, float]
    bootstrap: dict[str, Any] = Field(default_factory=dict)


class PromotionDecision(StrictContract):
    candidate_model_id: str
    champion_model_id: str
    decision: str
    reasons: list[str]
    gates: dict[str, bool]

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CalibrationConfig(StrictModel):
    run_id: str = Field(min_length=1, max_length=128)
    source_candidate: str = Field(default="chronos2", min_length=1, max_length=128)
    position_columns: tuple[str, ...] = Field(min_length=1)
    horizon: int = Field(default=1, gt=0)
    candidate_min: int
    candidate_max: int
    allow_duplicates: bool = False
    sort_policy: str = "ascending"
    position_ranges: dict[str, tuple[int, int]] = Field(default_factory=dict)
    min_fit_folds: int = Field(default=3, gt=0)
    min_conformal_folds: int = Field(default=2, gt=0)
    conformal_fraction: float = Field(default=0.4, gt=0.0, lt=1.0)
    interval_coverages: tuple[float, ...] = (0.8, 0.9)
    quantile_levels: tuple[float, ...] = (0.05, 0.1, 0.5, 0.9, 0.95)
    bias_statistic: str = "mean"
    quantile_correction_method: str = "linear"
    conformal_quantile_method: str = "higher"

    @field_validator("position_columns")
    @classmethod
    def validate_positions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("position_columns must be unique")
        return value

    @field_validator("interval_coverages")
    @classmethod
    def validate_coverages(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if not value:
            raise ValueError("interval_coverages must not be empty")
        if len(set(value)) != len(value):
            raise ValueError("interval_coverages must be unique")
        if any(level <= 0.0 or level >= 1.0 for level in value):
            raise ValueError("interval coverages must be strictly between 0 and 1")
        return tuple(sorted(value))

    @field_validator("quantile_levels")
    @classmethod
    def validate_quantiles(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if not value:
            raise ValueError("quantile_levels must not be empty")
        if len(set(value)) != len(value):
            raise ValueError("quantile_levels must be unique")
        if any(level <= 0.0 or level >= 1.0 for level in value):
            raise ValueError("quantile levels must be strictly between 0 and 1")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def validate_contract(self) -> CalibrationConfig:
        if self.candidate_max < self.candidate_min:
            raise ValueError("candidate_max must be >= candidate_min")
        if self.sort_policy not in {"ascending", "preserve"}:
            raise ValueError("sort_policy must be ascending or preserve")
        if self.bias_statistic not in {"mean", "median"}:
            raise ValueError("bias_statistic must be mean or median")
        if self.quantile_correction_method not in {"linear", "higher"}:
            raise ValueError("unsupported quantile_correction_method")
        if self.conformal_quantile_method != "higher":
            raise ValueError("conformal_quantile_method must be higher")
        required_levels: set[float] = {0.5}
        for coverage in self.interval_coverages:
            alpha = 1.0 - coverage
            required_levels.add(round(alpha / 2.0, 10))
            required_levels.add(round(1.0 - alpha / 2.0, 10))
        missing = sorted(required_levels - set(self.quantile_levels))
        if missing:
            raise ValueError(
                "quantile_levels must contain median and interval endpoints: "
                f"{missing}"
            )
        if self.position_ranges:
            if set(self.position_ranges) != set(self.position_columns):
                raise ValueError("position_ranges must exactly cover position_columns")
            for name, bounds in self.position_ranges.items():
                if len(bounds) != 2 or bounds[1] < bounds[0]:
                    raise ValueError(f"invalid position range for {name}")
                if bounds[0] < self.candidate_min or bounds[1] > self.candidate_max:
                    raise ValueError(f"position range for {name} is outside candidate domain")
        return self


@dataclass(frozen=True)
class CalibrationResult:
    report: dict[str, Any]
    split_assignments: pd.DataFrame
    parameters: pd.DataFrame
    predictions: pd.DataFrame
    metrics: pd.DataFrame
    position_metrics: pd.DataFrame
    seed_summary: pd.DataFrame
    comparison: pd.DataFrame


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

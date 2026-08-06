from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OOFConfig(StrictModel):
    run_id: str = Field(min_length=1, max_length=128)
    position_columns: tuple[str, ...] = Field(min_length=1)
    candidate_min: int
    candidate_max: int
    allow_duplicates: bool = False
    sort_policy: str = "ascending"
    position_ranges: dict[str, tuple[int, int]] = Field(default_factory=dict)
    min_train_size: int = Field(gt=1)
    horizon: int = Field(default=1, gt=0)
    step_size: int = Field(default=1, gt=0)
    allow_validation_overlap: bool = False
    require_gap_free_draw_no: bool = True
    seeds: tuple[int, ...] = (1, 2, 3)
    seasonal_period: int = Field(default=1, gt=0)
    quantile_levels: tuple[float, ...] = (0.1, 0.5, 0.9)
    fixed_values: tuple[float, ...] | None = None

    @field_validator("position_columns")
    @classmethod
    def validate_positions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("position_columns must be unique")
        return value

    @field_validator("seeds")
    @classmethod
    def validate_seeds(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value:
            raise ValueError("seeds must not be empty")
        if len(set(value)) != len(value):
            raise ValueError("seeds must be unique")
        return value

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
    def validate_contract(self) -> OOFConfig:
        if self.candidate_max < self.candidate_min:
            raise ValueError("candidate_max must be >= candidate_min")
        if self.sort_policy not in {"ascending", "preserve"}:
            raise ValueError("sort_policy must be ascending or preserve")
        if not self.allow_validation_overlap and self.step_size < self.horizon:
            raise ValueError("step_size must be >= horizon when overlap is disabled")
        if self.fixed_values is not None and len(self.fixed_values) != len(
            self.position_columns
        ):
            raise ValueError("fixed_values length must equal position count")
        if self.position_ranges:
            if set(self.position_ranges) != set(self.position_columns):
                raise ValueError("position_ranges must exactly cover position_columns")
            for name, bounds in self.position_ranges.items():
                if len(bounds) != 2 or bounds[1] < bounds[0]:
                    raise ValueError(f"invalid position range for {name}")
                if bounds[0] < self.candidate_min or bounds[1] > self.candidate_max:
                    raise ValueError(f"position range for {name} is outside candidate domain")
        return self


class PredictionBundle(StrictModel):
    point: tuple[tuple[float, ...], ...]
    quantiles: dict[str, tuple[tuple[float, ...], ...]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Predictor(Protocol):
    def __call__(
        self,
        history: pd.DataFrame,
        *,
        horizon: int,
        seed: int,
        fold_id: str,
    ) -> PredictionBundle: ...


@dataclass(frozen=True)
class Fold:
    fold_id: str
    train_start: int
    train_end: int
    validation_start: int
    validation_end: int


@dataclass(frozen=True)
class EvaluationResult:
    report: dict[str, Any]
    folds: pd.DataFrame
    predictions: pd.DataFrame
    metrics: pd.DataFrame
    position_metrics: pd.DataFrame
    seed_summary: pd.DataFrame
    baseline_comparison: pd.DataFrame


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_rolling_folds(total_rows: int, config: OOFConfig) -> tuple[Fold, ...]:
    if total_rows < config.min_train_size + config.horizon:
        raise ValueError("history is too short for the requested OOF configuration")
    folds: list[Fold] = []
    validation_start = config.min_train_size
    index = 0
    while validation_start + config.horizon <= total_rows:
        folds.append(
            Fold(
                fold_id=f"fold-{index:04d}",
                train_start=0,
                train_end=validation_start,
                validation_start=validation_start,
                validation_end=validation_start + config.horizon,
            )
        )
        validation_start += config.step_size
        index += 1
    return tuple(folds)

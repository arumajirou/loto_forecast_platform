from __future__ import annotations

import math
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProviderOperation(StrEnum):
    """Supported subprocess operations."""

    INVENTORY = "inventory"
    NAIVE_SMOKE = "naive_smoke"


class ProviderStatus(StrEnum):
    """Fail-closed provider result states."""

    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


class ProviderRequest(BaseModel):
    """Version-independent request crossing the sktime process boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: ProviderOperation
    output_dir: str = Field(min_length=1)
    environment_lane: Literal["core-py313"] = "core-py313"
    expected_sktime_version: str = "1.0.1"
    model_name: Literal["NaiveForecaster"] = "NaiveForecaster"
    strategy: Literal["last", "mean", "drift"] = "last"
    forecast_horizon: list[int] = Field(default_factory=lambda: [1], min_length=1)
    series: list[float] = Field(
        default_factory=lambda: [1.0, 2.0, 3.0, 4.0],
        min_length=3,
    )
    save_load: bool = True
    device: Literal["cpu"] = "cpu"
    seed: int = 1

    @field_validator("forecast_horizon")
    @classmethod
    def validate_forecast_horizon(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values):
            raise ValueError("forecast_horizon must contain positive relative steps")
        if len(values) != len(set(values)):
            raise ValueError("forecast_horizon must not contain duplicate steps")
        if values != sorted(values):
            raise ValueError("forecast_horizon must be sorted")
        return values

    @field_validator("series")
    @classmethod
    def validate_series(cls, values: list[float]) -> list[float]:
        if not all(math.isfinite(value) for value in values):
            raise ValueError("series must contain only finite values")
        return values


class ProviderResponse(BaseModel):
    """Durable response emitted for both successful and failed operations."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    status: ProviderStatus
    operation: ProviderOperation
    provider: Literal["sktime"] = "sktime"
    environment_lane: Literal["core-py313"] = "core-py313"
    expected_sktime_version: str
    actual_sktime_version: str | None = None
    inventory: dict[str, Any] | None = None
    smoke: dict[str, Any] | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)
    error: dict[str, str] | None = None

from __future__ import annotations

import math
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProviderOperation(StrEnum):
    """Operations supported by the isolated BasicTS provider."""

    IDENTITY = "identity"
    VALIDATE_CONFIG = "validate_config"
    DLINEAR_SMOKE = "dlinear_smoke"


class ProviderStatus(StrEnum):
    """Fail-closed execution states."""

    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


class ImportReference(BaseModel):
    """One class or function referenced by a serialized BasicTS configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    module: str = Field(min_length=1)
    name: str = Field(min_length=1)

    @field_validator("module", "name")
    @classmethod
    def reject_unsafe_syntax(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("import reference values must not contain surrounding whitespace")
        if value.startswith(".") or ".." in value:
            raise ValueError("relative import syntax is forbidden")
        if value.startswith("__") or value.endswith("__"):
            raise ValueError("dunder import references are forbidden")
        return value


class ProviderRequest(BaseModel):
    """Request crossing the root-to-BasicTS subprocess boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: ProviderOperation
    output_dir: str = Field(min_length=1)
    environment_lane: Literal["basicts-py311"] = "basicts-py311"
    expected_basicts_version: Literal["1.1.0"] = "1.1.0"
    expected_upstream_revision: Literal["c2bb6e31e591167e84459775a21a62e70a5893ce"] = (
        "c2bb6e31e591167e84459775a21a62e70a5893ce"
    )
    import_references: list[ImportReference] = Field(default_factory=list)
    series: list[list[float]] = Field(
        default_factory=lambda: [[float(index)] for index in range(1, 17)],
        min_length=4,
    )
    input_len: int = Field(default=8, ge=2)
    output_len: int = Field(default=1, ge=1)
    moving_avg: int = Field(default=3, ge=1)
    individual: bool = False
    training_steps: int = Field(default=3, ge=1, le=100)
    learning_rate: float = Field(default=1e-3, gt=0.0, le=1.0)
    save_load: bool = True
    device: Literal["cpu"] = "cpu"
    seed: int = 1

    @field_validator("series")
    @classmethod
    def validate_series(cls, rows: list[list[float]]) -> list[list[float]]:
        widths = {len(row) for row in rows}
        if len(widths) != 1 or not widths or 0 in widths:
            raise ValueError("series must be a non-empty rectangular matrix")
        if not all(math.isfinite(value) for row in rows for value in row):
            raise ValueError("series must contain only finite values")
        return rows

    @field_validator("moving_avg")
    @classmethod
    def validate_moving_average(cls, value: int) -> int:
        if value % 2 == 0:
            raise ValueError("moving_avg must be odd")
        return value

    @model_validator(mode="after")
    def validate_window_geometry(self) -> ProviderRequest:
        required = self.input_len + self.output_len
        if len(self.series) < required:
            raise ValueError("series must contain at least input_len + output_len rows")
        if self.moving_avg > self.input_len:
            raise ValueError("moving_avg must not exceed input_len")
        return self


class ProviderResponse(BaseModel):
    """Durable response emitted for both successful and failed operations."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    status: ProviderStatus
    operation: ProviderOperation
    provider: Literal["basicts"] = "basicts"
    environment_lane: Literal["basicts-py311"] = "basicts-py311"
    expected_basicts_version: str
    actual_basicts_version: str | None = None
    expected_upstream_revision: str
    actual_upstream_revision: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)
    error: dict[str, str] | None = None

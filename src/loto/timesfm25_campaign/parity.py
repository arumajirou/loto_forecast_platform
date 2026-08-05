from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from loto.adapters.timesfm25.contracts import Backend


class BackendParityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left_backend: Backend
    right_backend: Backend
    series_count: int = Field(ge=1)
    horizon: int = Field(ge=1)
    median_max_abs_diff: float = Field(ge=0)
    mean_max_abs_diff: float = Field(ge=0)
    quantile_max_abs_diff: float = Field(ge=0)
    tolerance: float = Field(gt=0)
    status: str
    notes: list[str] = Field(default_factory=list)

    @classmethod
    def from_differences(
        cls,
        *,
        left_backend: Backend,
        right_backend: Backend,
        series_count: int,
        horizon: int,
        median_max_abs_diff: float,
        mean_max_abs_diff: float,
        quantile_max_abs_diff: float,
        tolerance: float,
    ) -> BackendParityResult:
        maximum = max(median_max_abs_diff, mean_max_abs_diff, quantile_max_abs_diff)
        return cls(
            left_backend=left_backend,
            right_backend=right_backend,
            series_count=series_count,
            horizon=horizon,
            median_max_abs_diff=median_max_abs_diff,
            mean_max_abs_diff=mean_max_abs_diff,
            quantile_max_abs_diff=quantile_max_abs_diff,
            tolerance=tolerance,
            status="PASS" if maximum <= tolerance else "FAILED",
        )

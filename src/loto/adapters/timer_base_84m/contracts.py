from __future__ import annotations

import math
from datetime import date
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from loto.timer_base_84m_campaign.chronology import TimeAxis, validate_chronology
from loto.timer_base_84m_campaign.geometry import Game, geometry_for
from loto.timer_base_84m_campaign.provenance import (
    LICENSE,
    MODEL_ID,
    MODEL_REVISION,
    REPO_ID,
    SOURCE_REVISION,
    TRANSFORMERS_VERSION,
    WEIGHT_SHA256,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_assignment=True,
    )


class ArtifactPaths(StrictModel):
    request_path: str
    response_path: str
    snapshot_path: str
    manifest_path: str

    @field_validator("request_path", "response_path", "snapshot_path", "manifest_path")
    @classmethod
    def validate_safe_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or value.strip() != value or not value:
            raise ValueError("artifact paths must be non-empty safe relative POSIX paths")
        return value


class ChronologyEvidence(StrictModel):
    time_axis: TimeAxis
    cutoff_draw_no: int = Field(ge=1)
    cutoff_date: date
    draw_numbers: tuple[int, ...]
    dates: tuple[date, ...]
    mapping_sha256: str
    future_actuals_present: Literal[False]
    duplicate_free: Literal[True]
    strictly_increasing: Literal[True]
    gap_free: Literal[True]


class TimerRequest(StrictModel):
    schema_version: Literal["timer-base-84m.request.v1"]
    run_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    operation: Literal[
        "identity",
        "validate_request",
        "validate_environment",
        "resolve_snapshot_manifest",
        "inspect_properties",
        "load",
        "predict",
    ]
    model_id: Literal[MODEL_ID]
    repo_id: Literal[REPO_ID]
    package_version: Literal[TRANSFORMERS_VERSION]
    source_revision: Literal[SOURCE_REVISION]
    model_revision: Literal[MODEL_REVISION]
    config_sha256: Literal["UNVERIFIED"]
    weight_sha256: Literal[WEIGHT_SHA256]
    license: Literal[LICENSE]
    game: Game
    target_layout: Literal["position_univariate", "position_panel_batched_univariate"]
    context_length: int
    prediction_length: Literal[1, 2, 5]
    seed: int = Field(ge=0, le=2**32 - 1)
    requested_device: Literal["cpu", "cuda"]
    input_shape: tuple[int, int]
    series: tuple[tuple[float, ...], ...]
    past_covariates: None
    known_future_covariates: None
    chronology_evidence: ChronologyEvidence
    actuals_used: Literal[False]
    artifact_paths: ArtifactPaths

    @model_validator(mode="after")
    def validate_timer_contract(self) -> "TimerRequest":
        if not 96 <= self.context_length <= 2880:
            raise ValueError("context_length must be within 96..2880")
        if self.context_length % 96 != 0:
            raise ValueError("context_length must be an exact multiple of patch length 96")
        geometry = geometry_for(self.game)
        expected_shape = (geometry.position_count, self.context_length)
        if self.input_shape != expected_shape:
            raise ValueError(f"input_shape must equal {expected_shape}")
        if len(self.series) != geometry.position_count:
            raise ValueError("series count does not match game geometry")
        if any(len(values) != self.context_length for values in self.series):
            raise ValueError("every univariate series must match context_length")
        if any(not math.isfinite(value) for values in self.series for value in values):
            raise ValueError("input series contain non-finite values")
        evidence = self.chronology_evidence
        if len(evidence.draw_numbers) != self.context_length:
            raise ValueError("chronology evidence length must match context_length")
        mapping_sha256 = validate_chronology(
            game=self.game,
            time_axis=evidence.time_axis,
            draw_numbers=evidence.draw_numbers,
            dates=evidence.dates,
            cutoff_draw_no=evidence.cutoff_draw_no,
            cutoff_date=evidence.cutoff_date,
            actuals_used=self.actuals_used or evidence.future_actuals_present,
        )
        if evidence.mapping_sha256 != mapping_sha256:
            raise ValueError("chronology mapping SHA-256 mismatch")
        return self


class TimerResponse(StrictModel):
    schema_version: Literal["timer-base-84m.response.v1"]
    run_id: str
    status: Literal[
        "IDENTITY",
        "VALIDATED",
        "ENVIRONMENT_VALIDATED",
        "SNAPSHOT_MANIFEST_VALIDATED",
        "EXECUTION_PENDING",
    ]
    model_id: Literal[MODEL_ID]
    package_version: Literal[TRANSFORMERS_VERSION]
    source_revision: Literal[SOURCE_REVISION]
    model_revision: Literal[MODEL_REVISION]
    config_sha256: Literal["UNVERIFIED"]
    weight_sha256: Literal[WEIGHT_SHA256]
    license: Literal[LICENSE]
    game: Game
    target_layout: Literal["position_univariate", "position_panel_batched_univariate"]
    context_length: int
    prediction_length: Literal[1, 2, 5]
    seed: int
    requested_device: Literal["cpu", "cuda"]
    effective_device: None
    cpu_fallback: Literal[False]
    input_shape: tuple[int, int]
    output_shape: None
    point_forecast: None
    quantiles: None
    samples: None
    finite_check: None
    chronology_evidence: ChronologyEvidence
    actuals_used: Literal[False]
    runtime_pid: None
    gpu_uuid: None
    gpu_process_vram_bytes: None
    artifact_paths: ArtifactPaths

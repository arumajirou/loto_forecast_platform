"""Pydantic contracts for database NeuralForecast runtime verification."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelRuntimeVerification(BaseModel):
    """Verification result for one database AutoModel directory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str
    class_name: str | None = None
    status: Literal["PASS", "FAIL"]
    model_status: str | None = None
    certification_status: str | None = None
    search_space_status: str
    runtime_status: str
    profile_sha256: str | None = None
    runtime_certification_sha256: str | None = None
    critical_artifacts: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()


class DatabaseRuntimeVerificationReport(BaseModel):
    """Serializable root report for one database runtime campaign."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0.0"
    created_at: str
    run_directory: str
    status: Literal["PASS", "FAIL"]
    require_gpu: bool
    expected_model_count: int
    observed_model_count: int
    campaign_status: str | None = None
    certification_status: str | None = None
    search_space_artifact_status: str | None = None
    model_results: tuple[ModelRuntimeVerification, ...] = ()
    failures: tuple[str, ...] = ()


class ArtifactManifest(BaseModel):
    """Critical artifact inventory for a verified runtime campaign."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0.0"
    created_at: str
    run_directory: str
    verification_status: Literal["PASS", "FAIL"]
    files: tuple[dict[str, Any], ...] = Field(default_factory=tuple)

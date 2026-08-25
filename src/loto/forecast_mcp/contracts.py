"""Strict contracts for the Forecast MCP bridge.

The LLM-facing request deliberately contains no command, shell, path, history,
actual, Holdout, Prospective, or residency-mode fields. Operator-controlled paths
and GPU residency policy live only in server configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from loto.gpu_exclusive.models import (
    ExternalGateConfig,
    GpuProbeConfig,
    GpuResidencyPolicy,
    HttpRuntimeConfig,
)

MOIRAI2_REPO_ID = "Salesforce/moirai-2.0-R-small"
MOIRAI2_REVISION = "30f43ff08c8494f4943ae1521e9d4e94a0fbb389"
MOIRAI2_MODEL_ID = "moirai2-0-r-small"


class ForecastToolRequest(BaseModel):
    """Only the single formally allowed route is exposed to the LLM."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    game: Literal["numbers3"] = "numbers3"
    model: Literal["moirai2"] = "moirai2"
    horizon: Literal[1] = 1
    device: Literal["cuda"] = "cuda"
    scope: Literal["development"] = "development"


class DevelopmentRequestManifest(BaseModel):
    """Operator-reviewed binding for the provider request template."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    data_scope: Literal["development"]
    actuals_used: Literal[False]
    holdout_used: Literal[False]
    prospective_used: Literal[False]
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ServerBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: Literal[18778] = 18778
    artifact_root: Path


class Moirai2RouteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repo_root: Path
    provider_python: Path
    provider_script: Path
    approved_request: Path
    request_manifest: Path
    runtime_lane: Literal["cuda13-experimental"] = "cuda13-experimental"
    timeout_seconds: float = Field(default=900.0, gt=0)
    expected_repo_id: Literal[MOIRAI2_REPO_ID] = MOIRAI2_REPO_ID
    expected_revision: Literal[MOIRAI2_REVISION] = MOIRAI2_REVISION


class ForecastMcpConfig(BaseModel):
    """Operator-only service configuration; never accepted from MCP tool input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    server: ServerBinding
    route: Moirai2RouteConfig
    qwen: HttpRuntimeConfig
    gpu: GpuProbeConfig
    gate: ExternalGateConfig
    residency: GpuResidencyPolicy = Field(default_factory=GpuResidencyPolicy)
    lock_path: Path = Path("/tmp/loto-gpu-exclusive.lock")

"""Strict contracts for the Forecast MCP bridge.

The LLM-facing request deliberately contains no command, shell, path, history,
actual, Holdout, Prospective, or residency-mode fields. Operator-controlled paths
and GPU residency policy live only in server configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loto.gpu_exclusive.models import (
    ExternalGateConfig,
    GpuProbeConfig,
    GpuResidencyPolicy,
    HttpRuntimeConfig,
)

MOIRAI2_REPO_ID = "Salesforce/moirai-2.0-R-small"
MOIRAI2_REVISION = "30f43ff08c8494f4943ae1521e9d4e94a0fbb389"
MOIRAI2_MODEL_ID = "moirai2-0-r-small"
APPROVED_REQUEST_NAME = "numbers3-development-request.json"
REQUEST_MANIFEST_NAME = "numbers3-development-request.manifest.json"


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
    """Operator route with one source of truth for approved runtime artifacts.

    New configuration supplies only ``operator_runtime_root``. For migration,
    the legacy ``approved_request`` and ``request_manifest`` keys are accepted
    only when they identify the exact canonical filenames in the same directory;
    they are normalized into ``operator_runtime_root`` before validation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    repo_root: Path
    provider_python: Path
    provider_script: Path
    operator_runtime_root: Path
    runtime_lane: Literal["cuda13-experimental"] = "cuda13-experimental"
    timeout_seconds: float = Field(default=900.0, gt=0)
    expected_repo_id: Literal[MOIRAI2_REPO_ID] = MOIRAI2_REPO_ID
    expected_revision: Literal[MOIRAI2_REVISION] = MOIRAI2_REVISION

    @model_validator(mode="before")
    @classmethod
    def normalize_operator_artifact_paths(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        root_value = payload.get("operator_runtime_root")
        legacy_request = payload.pop("approved_request", None)
        legacy_manifest = payload.pop("request_manifest", None)

        if (legacy_request is None) != (legacy_manifest is None):
            raise ValueError(
                "legacy approved_request and request_manifest must be supplied together"
            )

        root = Path(root_value).expanduser() if root_value is not None else None

        if legacy_request is not None and legacy_manifest is not None:
            request_path = Path(legacy_request).expanduser()
            manifest_path = Path(legacy_manifest).expanduser()
            if request_path.name != APPROVED_REQUEST_NAME:
                raise ValueError("legacy approved_request filename is not canonical")
            if manifest_path.name != REQUEST_MANIFEST_NAME:
                raise ValueError("legacy request_manifest filename is not canonical")
            if request_path.parent != manifest_path.parent:
                raise ValueError("operator approved request/manifest path drift detected")

            legacy_root = request_path.parent
            if root is None:
                root = legacy_root
            elif root != legacy_root:
                raise ValueError("operator_runtime_root conflicts with legacy artifact paths")

        if root is None:
            raise ValueError("operator_runtime_root is required")
        if not root.is_absolute():
            raise ValueError("operator_runtime_root must be an absolute path")

        # Keep the pre-validator output JSON-compatible. Pydantic 2.13 rejects a
        # Path injected by a before-validator while model_validate_json() is still
        # in JSON mode. The field validator will convert this string back to Path.
        payload["operator_runtime_root"] = str(root)
        return payload

    @property
    def approved_request(self) -> Path:
        """Canonical operator-approved development request path."""

        return self.operator_runtime_root / APPROVED_REQUEST_NAME

    @property
    def request_manifest(self) -> Path:
        """Canonical SHA-binding manifest path for the approved request."""

        return self.operator_runtime_root / REQUEST_MANIFEST_NAME


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

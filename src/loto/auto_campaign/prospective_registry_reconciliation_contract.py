"""Contracts for read-only Prospective registry reconciliation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

RECONCILIATION_SCHEMA_VERSION = "all-auto-prospective-registry-reconciliation-v1"
RECONCILIATION_EXPECTED = "RECONCILIATION_EXPECTED.json"
POSTGRES_SNAPSHOT = "POSTGRES_SNAPSHOT.json"
MLFLOW_SNAPSHOT = "MLFLOW_SNAPSHOT.json"
RECONCILIATION_REPORT = "RECONCILIATION_REPORT.json"
RECONCILIATION_MANIFEST = "ARTIFACT_MANIFEST.json"


class ReconciliationOptions(BaseModel):
    """Validated read-only backend reconciliation policy."""

    model_config = ConfigDict(extra="forbid")

    postgres_dsn_env: str | None = Field(default=None, max_length=200)
    mlflow_uri: str | None = None
    mlflow_uri_env: str | None = Field(default=None, max_length=200)
    float_tolerance: float = Field(default=1e-12, ge=0.0, le=1e-3)
    require_remote_artifacts: bool = True


@dataclass(frozen=True)
class ReconciliationBackendFunctions:
    """Injectable read-only backend probes for focused tests."""

    query_postgres: Callable[
        [str, dict[str, Any]],
        dict[str, Any],
    ]
    query_mlflow: Callable[..., dict[str, Any]]

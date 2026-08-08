"""Contracts and normalized identities for Prospective registration."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .prospective_registry_backends import (
    finalize_postgres,
    mark_postgres_blocked,
    prepare_postgres,
    record_mlflow,
)

REGISTRY_SCHEMA_VERSION = "all-auto-prospective-registry-v1"
REGISTRY_PAYLOAD = "REGISTRY_PAYLOAD.json"
REGISTRY_REPORT = "REGISTRY_REPORT.json"
BACKEND_RECEIPTS = "BACKEND_RECEIPTS.json"
REGISTRY_MANIFEST = "ARTIFACT_MANIFEST.json"


class RegistryOptions(BaseModel):
    """Validated operator policy for dual-sink registration."""

    model_config = ConfigDict(extra="forbid")

    registry_namespace: str = Field(
        default="production",
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    postgres_dsn_env: str = Field(
        default="LOTO_POSTGRES_DSN",
        min_length=1,
        max_length=200,
        pattern=r"^[A-Z_][A-Z0-9_]*$",
    )
    mlflow_uri: str | None = None
    mlflow_uri_env: str = Field(
        default="MLFLOW_TRACKING_URI",
        min_length=1,
        max_length=200,
        pattern=r"^[A-Z_][A-Z0-9_]*$",
    )
    mlflow_experiment: str = Field(
        default="loto-neuralforecast-prospective",
        min_length=1,
        max_length=250,
    )
    artifact_mode: Literal["metadata", "full"] = "metadata"
    require_postgres: bool = True
    require_mlflow: bool = True

    @model_validator(mode="after")
    def validate_required_backends(self) -> RegistryOptions:
        if not self.require_postgres or not self.require_mlflow:
            raise ValueError("formal prospective registration requires both PostgreSQL and MLflow")
        return self


@dataclass(frozen=True)
class RegistryBackendFunctions:
    """Injectable backend operations for focused tests."""

    prepare_postgres: Callable[
        [str, dict[str, Any], dict[str, pd.DataFrame]],
        dict[str, Any],
    ] = prepare_postgres
    record_mlflow: Callable[..., dict[str, Any]] = record_mlflow
    finalize_postgres: Callable[
        [str, dict[str, Any], dict[str, Any]],
        dict[str, Any],
    ] = finalize_postgres
    mark_postgres_blocked: Callable[
        [str, dict[str, Any], dict[str, Any]],
        dict[str, Any],
    ] = mark_postgres_blocked


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {type(exc).__name__}: {exc}") from exc
    if not isinstance(payload, dict) or not payload:
        raise ValueError(f"{label} must be a non-empty JSON object")
    return payload


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def _record_json(row: Mapping[str, Any]) -> str:
    return json.dumps(
        {key: _json_safe(value) for key, value in row.items()},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _component(value: Any) -> str:
    safe = _json_safe(value)
    return "NONE" if safe is None else str(safe)


def _candidate_key(row: Mapping[str, Any]) -> str:
    return "|".join(
        (
            _component(row.get("source_type")),
            _component(row.get("model_name")),
            _component(row.get("baseline_name")),
            _component(row.get("track")),
        )
    )


def _seed_token(value: Any) -> str:
    safe = _json_safe(value)
    return "NONE" if safe is None else str(int(safe))

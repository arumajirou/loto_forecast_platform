from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from loto.orchestration.pipeline_downstream_preflight_errors import (
    DownstreamCommitPreflightError,
)

REQUIRED_DEFERRED_OPERATIONS = frozenset(
    {
        "Registry.record_stage",
        "Registry.record_forecast",
        "PlatformRegistry.create_run/update_run/register_forecast/register_model",
        "MlflowBridge.record_run",
        "create_release_bundle",
        "ArtifactStore.put_file",
        "EventPublisher.publish",
    }
)

IMMUTABLE_ARTIFACTS = (
    "canonical.csv",
    "dataset_manifest.json",
    "candidate_features.csv",
    "feature_manifest.json",
    "evaluation.json",
    "forecast.json",
    "forecast.sealed.json",
    "resource_evidence.json",
    "pipeline_data_access_ledger.json",
    "pipeline_data_access_validation.json",
    "pipeline_data_access_report.json",
    "downstream_commit_plan.json",
)


class StagedCommitPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: str
    run_id: str
    ledger_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executed: bool
    deferred_operations: list[str]
    reason: str


JsonValidator = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
SealVerifier = Callable[[dict[str, Any], bytes], bool]


def absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def reject_symlink_components(path: Path, *, label: str) -> None:
    absolute = absolute_path(path)
    for candidate in (absolute, *absolute.parents):
        if candidate.exists() and candidate.is_symlink():
            raise DownstreamCommitPreflightError(
                f"{label} must not contain a symlink component: {candidate}"
            )


def require_regular_file(path: Path, *, label: str) -> None:
    reject_symlink_components(path, label=label)
    if not path.is_file():
        raise DownstreamCommitPreflightError(f"{label} is not a regular file: {path}")


def load_json(path: Path) -> dict[str, Any]:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise DownstreamCommitPreflightError(f"duplicate JSON key in {path.name}: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
    except DownstreamCommitPreflightError:
        raise
    except Exception as exc:
        raise DownstreamCommitPreflightError(
            f"invalid JSON artifact {path.name}: {type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise DownstreamCommitPreflightError(f"JSON artifact must contain an object: {path.name}")
    return value


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

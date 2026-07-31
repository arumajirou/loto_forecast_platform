from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


class SubprocessProviderContractError(ValueError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


def validate_provider_request(request: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "model_id",
        "repo_id",
        "local_files_only",
        "device",
        "dtype",
        "history",
        "prediction_length",
    }
    missing = sorted(required - set(request))
    if missing:
        raise SubprocessProviderContractError("INVALID_REQUEST", f"missing request keys: {missing}")
    if int(request["schema_version"]) != 1:
        raise SubprocessProviderContractError(
            "INVALID_REQUEST",
            f"unsupported schema_version: {request['schema_version']}",
        )
    if not isinstance(request["history"], list) or not request["history"]:
        raise SubprocessProviderContractError("INVALID_REQUEST", "history must be a non-empty list")
    if int(request["prediction_length"]) < 1:
        raise SubprocessProviderContractError("INVALID_REQUEST", "prediction_length must be >= 1")


def validate_provider_response(
    response: dict[str, Any],
    *,
    expected_shape: tuple[int, ...] = (7,),
) -> np.ndarray:
    if response.get("status") != "OK":
        raise SubprocessProviderContractError(
            str(response.get("status", "ERROR")),
            str(response.get("message", "provider failed")),
        )
    if int(response.get("schema_version", 0)) != 1:
        raise SubprocessProviderContractError(
            "INVALID_RESPONSE",
            f"unsupported schema_version: {response.get('schema_version')}",
        )
    if "provider_version" not in response:
        raise SubprocessProviderContractError("INVALID_RESPONSE", "provider_version is required")
    predictions = np.asarray(response.get("predictions"), dtype=float)
    if predictions.shape != expected_shape:
        raise SubprocessProviderContractError(
            "INVALID_PREDICTION",
            f"prediction shape mismatch: expected={expected_shape}, actual={predictions.shape}",
        )
    if not bool(response.get("finite", np.isfinite(predictions).all())):
        raise SubprocessProviderContractError(
            "INVALID_PREDICTION",
            "provider reported non-finite predictions",
        )
    if not np.isfinite(predictions).all():
        raise SubprocessProviderContractError(
            "INVALID_PREDICTION",
            "predictions contain NaN or Inf",
        )
    artifact = response.get("artifact_reference")
    if not isinstance(artifact, dict):
        raise SubprocessProviderContractError(
            "ARTIFACT_MISSING",
            "artifact_reference must be present",
        )
    snapshot = artifact.get("snapshot_path")
    if snapshot is not None and not Path(str(snapshot)).exists():
        raise SubprocessProviderContractError(
            "MODEL_WEIGHTS_MISSING",
            f"snapshot_path does not exist: {snapshot}",
        )
    properties = response.get("properties")
    if not isinstance(properties, dict) or not properties.get("license"):
        raise SubprocessProviderContractError(
            "PROPERTY_INSPECTION_FAILED",
            "license metadata is required",
        )
    if not properties.get("weight_sha256") or not properties.get("config_sha256"):
        raise SubprocessProviderContractError(
            "ARTIFACT_MISSING",
            "weight_sha256 and config_sha256 are required",
        )
    if not isinstance(response.get("gpu_evidence"), dict):
        raise SubprocessProviderContractError("GPU_PARTIAL", "gpu_evidence must be present")
    return predictions

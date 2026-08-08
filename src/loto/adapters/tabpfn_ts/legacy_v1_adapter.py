from __future__ import annotations

import math
from typing import Any

from .contract import (
    Device,
    HistorySeries,
    OutputSelection,
    TabPFNTSRequestV2,
    TabPFNTSResponseV2,
    TaskFormulation,
    TimeSemantics,
)
from .geometry import geometry_for
from .manifests import (
    V2_REPO_ID,
    V2_REVISION,
    V2_WEIGHT_FILENAME,
    CheckpointLane,
)

LEGACY_V1_ALLOWED_KEYS = {
    "schema_version",
    "model_id",
    "repo_id",
    "revision",
    "weight_filename",
    "snapshot_path",
    "local_files_only",
    "device",
    "dtype",
    "history",
    "prediction_length",
    "run_id",
}


def legacy_v1_request_to_v2(payload: dict[str, Any]) -> TabPFNTSRequestV2:
    unknown = sorted(set(payload) - LEGACY_V1_ALLOWED_KEYS)
    if unknown:
        raise ValueError(f"unknown legacy schema-v1 keys: {unknown}")
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("legacy request schema_version must be 1")
    if payload.get("repo_id") != V2_REPO_ID:
        raise ValueError("legacy request repo_id does not match the trusted V2 lane")
    if payload.get("revision") != V2_REVISION:
        raise ValueError("legacy request revision does not match the trusted V2 lane")
    if payload.get("weight_filename") != V2_WEIGHT_FILENAME:
        raise ValueError("legacy request checkpoint filename is not trusted")
    if payload.get("local_files_only") is not True:
        raise ValueError("legacy request local_files_only must be true")
    if int(payload.get("prediction_length", 0)) != 1:
        raise ValueError("legacy schema-v1 compatibility supports prediction_length=1 only")

    records = payload.get("history")
    if not isinstance(records, list) or not records:
        raise ValueError("legacy history must be a non-empty list")

    timestamps: list[str] = []
    selected_by_row: list[set[int]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"legacy history row {index} must be an object")
        required = {"draw_date", *(f"n{i}" for i in range(1, 8))}
        missing = sorted(required - set(record))
        if missing:
            raise ValueError(f"legacy history row {index} missing keys: {missing}")
        timestamps.append(str(record["draw_date"]))
        selected_by_row.append({int(record[f"n{i}"]) for i in range(1, 8)})

    geometry = geometry_for("loto7")
    series_ids = [f"candidate-{candidate:02d}" for candidate in range(1, 38)]
    history = [
        HistorySeries(
            series_id=series_id,
            timestamps=timestamps,
            values=[float(candidate in selected) for selected in selected_by_row],
        )
        for candidate, series_id in zip(range(1, 38), series_ids, strict=True)
    ]

    requested_device = str(payload.get("device", "cpu"))
    return TabPFNTSRequestV2(
        run_id=str(payload.get("run_id") or "legacy-v1-adapter"),
        checkpoint_lane=CheckpointLane.V2_REG_LEGACY,
        repo_id=V2_REPO_ID,
        revision=V2_REVISION,
        task_formulation=TaskFormulation.CANDIDATE_SCORE,
        game_geometry=geometry,
        series_ids=series_ids,
        history=history,
        time_semantics=TimeSemantics.CALENDAR_TIME,
        feature_set_id="legacy-calendar-time",
        max_context_length=min(len(records), 32_768),
        prediction_length=1,
        quantile_levels=[0.5],
        output_selection=OutputSelection.MEDIAN,
        device=Device.CUDA if requested_device == "cuda" else Device.CPU,
        seed=1,
    )


def v2_response_to_legacy_v1(response: TabPFNTSResponseV2) -> dict[str, Any]:
    if response.status.value != "OK":
        return {
            "status": response.status.value,
            "schema_version": 1,
            "provider_version": 2,
            "message": "; ".join(response.warnings) or response.status.value,
        }
    if response.task_formulation is not TaskFormulation.CANDIDATE_SCORE:
        raise ValueError("legacy response conversion requires candidate_score formulation")
    if response.raw_candidate_scores is None:
        raise ValueError("legacy response conversion requires raw candidate scores")

    ordered = sorted(response.raw_candidate_scores, key=lambda item: item.candidate)
    predictions = [item.raw_candidate_regression_score for item in ordered]
    if len(predictions) != 37 or not all(math.isfinite(value) for value in predictions):
        raise ValueError("legacy response must contain 37 finite candidate scores")

    artifact = response.artifact_reference.model_dump(mode="json", exclude_none=True)
    properties = {
        "library": "tabpfn_time_series",
        "package": "tabpfn-time-series",
        "license": response.license_evidence.weight_license,
        "context_length": response.effective_arguments.effective_context_length,
        "prediction_length": response.effective_arguments.prediction_length,
        "weight_sha256": response.model_identity.checkpoint_sha256,
        "config_sha256": response.feature_manifest.config_sha256,
        "output_semantics": "raw_candidate_regression_scores",
    }
    return {
        "status": "OK",
        "schema_version": 1,
        "provider_version": 2,
        "repo_id": response.model_identity.repo_id,
        "snapshot_path": artifact.get("checkpoint_path"),
        "predictions": predictions,
        "prediction_shape": [37],
        "finite": True,
        "properties": properties,
        "gpu_evidence": response.gpu_evidence.model_dump(mode="json"),
        "artifact_reference": artifact,
    }

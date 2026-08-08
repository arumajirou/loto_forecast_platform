from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

import pandas as pd

from loto.adapters.chronos2.artifacts import write_json_atomic, write_sha256sums
from loto.adapters.chronos2.compatibility import adapt_schema_v1
from loto.adapters.chronos2.contracts import (
    Chronos2RequestV2,
    Chronos2ResponseV2,
    Operation,
)
from loto.adapters.chronos2.manifest import (
    CHRONOS_PACKAGE_SOURCE_REVISION,
    CHRONOS_PACKAGE_VERSION,
    build_model_manifest,
)
from loto.adapters.chronos2.runtime import PipelineLoader, run_prediction


def parse_request(payload: dict[str, Any]) -> Chronos2RequestV2:
    if int(payload.get("schema_version", 1)) == 1:
        return adapt_schema_v1(payload)
    return Chronos2RequestV2.model_validate(payload)


def _identity_response(request: Chronos2RequestV2) -> Chronos2ResponseV2:
    return Chronos2ResponseV2(
        status="OK",
        run_id=request.run_id,
        operation=request.operation,
        model_identity={
            "model_id": request.model_id,
            "repo_id": request.repo_id,
            "revision": request.revision,
            "package_version": CHRONOS_PACKAGE_VERSION,
            "package_source_revision": CHRONOS_PACKAGE_SOURCE_REVISION,
        },
        effective_arguments={"local_files_only": True},
    )


def _persist_response(
    request: Chronos2RequestV2,
    response: Chronos2ResponseV2,
) -> dict[str, Any]:
    if not request.artifact_dir:
        return {}
    root = Path(request.artifact_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    response_path = root / "response.json"
    write_json_atomic(response_path, response.model_dump(mode="json"))

    artifacts: dict[str, str] = {"response": str(response_path)}
    if response.status == "OK" and response.point_forecast:
        rows: list[dict[str, Any]] = []
        for position_index, series_id in enumerate(response.series_identity):
            for horizon_index, value in enumerate(response.point_forecast[position_index]):
                row = {
                    "series_id": series_id,
                    "horizon_step": horizon_index + 1,
                    "point": value,
                    "median": response.median_forecast[position_index][horizon_index],
                }
                for level, matrix in response.quantiles.items():
                    row[f"q_{level}"] = matrix[position_index][horizon_index]
                rows.append(row)
        prediction_path = root / "predictions.parquet"
        pd.DataFrame(rows).to_parquet(prediction_path, index=False)
        artifacts["predictions"] = str(prediction_path)

    if request.snapshot_path:
        manifest = build_model_manifest(
            request.snapshot_path,
            lane="current_reviewed",
            revision=request.revision,
        )
        manifest_path = root / "CHRONOS2_MODEL_MANIFEST.json"
        write_json_atomic(manifest_path, manifest.model_dump(mode="json"))
        artifacts["model_manifest"] = str(manifest_path)

    artifact_manifest = root / "ARTIFACT_MANIFEST.json"
    write_json_atomic(
        artifact_manifest,
        {
            "schema_version": 1,
            "run_id": request.run_id,
            "status": response.status,
            "artifacts": artifacts,
            "reference_manifest_save": bool(request.snapshot_path),
            "weight_snapshot_saved": False,
        },
    )
    artifacts["artifact_manifest"] = str(artifact_manifest)
    artifacts["sha256sums"] = str(write_sha256sums(root))
    return artifacts


def execute_request(
    payload: dict[str, Any],
    *,
    pipeline_loader: PipelineLoader | None = None,
) -> Chronos2ResponseV2:
    request: Chronos2RequestV2 | None = None
    try:
        request = parse_request(payload)
        if request.operation is Operation.IDENTITY:
            response = _identity_response(request)
        else:
            if request.operation is Operation.REFERENCE_RELOAD:
                manifest_path = Path(str(request.reference_manifest_path)).expanduser().resolve()
                if not manifest_path.is_file():
                    raise FileNotFoundError(f"reference manifest does not exist: {manifest_path}")
                manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_payload.get("revision") != request.revision:
                    raise ValueError("reference manifest revision does not match request")
            response = run_prediction(request, pipeline_loader=pipeline_loader)
        artifacts = _persist_response(request, response)
        if artifacts:
            response = response.model_copy(update={"artifact_reference": artifacts})
            write_json_atomic(
                Path(request.artifact_dir).expanduser().resolve() / "response.json",
                response.model_dump(mode="json"),
            )
            write_sha256sums(Path(request.artifact_dir).expanduser().resolve())
        return response
    except Exception as exc:
        run_id = request.run_id if request else str(payload.get("run_id", "unknown"))
        operation_value = payload.get("operation", "predict")
        try:
            operation = Operation(operation_value)
        except ValueError:
            operation = Operation.PREDICT
        response = Chronos2ResponseV2(
            status="ERROR",
            run_id=run_id,
            operation=operation,
            error={
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        if request and request.artifact_dir:
            _persist_response(request, response)
        return response

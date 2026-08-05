from __future__ import annotations

import os
from pathlib import Path

from loto.merlion_campaign.artifacts import resolve_under, verify_model_manifest
from loto.merlion_campaign.discovery import discover_factory_aliases
from loto.merlion_campaign.protocol import Operation, ProviderRequest, ProviderResponse
from loto.merlion_campaign.provenance import installed_identity
from loto.merlion_campaign.runtime import load_predict, train_save


def execute(request: ProviderRequest, work_root: Path) -> ProviderResponse:
    if request.operation is Operation.IDENTITY:
        identity = installed_identity()
        status = "PASS" if identity["version_match"] else "BLOCKED"
        return ProviderResponse(
            request_id=request.request_id,
            status=status,
            phase="identity",
            message="runtime identity verified" if status == "PASS" else "version mismatch",
            process_id=os.getpid(),
            evidence=identity,
        )
    if request.operation is Operation.DISCOVER:
        rows = [row.to_dict() for row in discover_factory_aliases()]
        return ProviderResponse(
            request_id=request.request_id,
            status="PASS",
            phase="discover",
            message="factory aliases discovered",
            process_id=os.getpid(),
            evidence={
                "model_count": len(rows),
                "models": rows,
            },
        )
    if request.operation is Operation.TRAIN_SAVE:
        prediction, evidence = train_save(request, work_root)
        return ProviderResponse(
            request_id=request.request_id,
            status="PASS",
            phase="train_save",
            message="model trained, forecasted, and saved",
            process_id=os.getpid(),
            evidence=evidence,
            prediction=prediction,
        )
    if request.operation is Operation.LOAD_PREDICT:
        prediction, evidence = load_predict(request, work_root)
        return ProviderResponse(
            request_id=request.request_id,
            status="PASS",
            phase="load_predict",
            message="trusted model loaded and forecast reproduced",
            process_id=os.getpid(),
            evidence=evidence,
            prediction=prediction,
        )
    if request.operation is Operation.VERIFY_ARTIFACT:
        if request.expected_manifest_sha256 is None:
            raise ValueError("verify_artifact requires expected_manifest_sha256")
        model_dir = resolve_under(work_root, request.artifact_subdir)
        manifest = verify_model_manifest(model_dir, request.expected_manifest_sha256)
        return ProviderResponse(
            request_id=request.request_id,
            status="PASS",
            phase="verify_artifact",
            message="trusted model artifact verified",
            process_id=os.getpid(),
            evidence=manifest,
        )
    raise ValueError(f"unsupported operation: {request.operation}")

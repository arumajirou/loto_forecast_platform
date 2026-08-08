from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .artifacts import finalize_manifest, write_json
from .discovery import discover_models
from .executor import execute_fit_predict
from .protocol import DartsRequest, DartsResponse, FailureClass


def _persist_bundle(request: DartsRequest, response: DartsResponse) -> None:
    root = request.artifact_dir
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "request.json", request.model_dump(mode="json"))
    write_json(root / "response.json", response.model_dump(mode="json"))
    if response.metrics is not None:
        write_json(root / "metrics.json", response.metrics)
    if response.baseline_metrics is not None:
        write_json(root / "baseline_metrics.json", response.baseline_metrics)
    if response.runtime_certification is not None:
        write_json(root / "runtime_certification.json", response.runtime_certification)
    if response.prospective_seal is not None:
        write_json(root / "prospective_seal.json", response.prospective_seal)
    finalize_manifest(root)


def _execute_request(request: DartsRequest, frame: pd.DataFrame | None) -> DartsResponse:
    if request.mode == "discover":
        return DartsResponse(
            run_id=request.run_id,
            status="SUCCEEDED",
            model_inventory=discover_models(),
            metadata={"static_public_export_count": 58, "runtime": request.runtime},
        )
    if frame is None:
        raise ValueError("fit_predict requires an input frame")
    result = execute_fit_predict(request, frame)
    predictions, ledger, metadata, metrics, baselines, certification, seal = result
    failed = []
    if request.persistence.verify_save_load and certification is not None:
        failed = [item for item in certification if item["status"] != "RUNTIME_CERTIFIED"]
    return DartsResponse(
        run_id=request.run_id,
        status="FAILED" if failed else "SUCCEEDED",
        failure_class=FailureClass.PERSISTENCE_FAILED if failed else None,
        message=(f"runtime certification failed for {len(failed)} position(s)" if failed else None),
        predictions=predictions,
        argument_ledger=ledger,
        metrics=metrics,
        baseline_metrics=baselines,
        runtime_certification=certification,
        prospective_seal=seal,
        metadata=metadata,
    )


def run_request(request: DartsRequest, *, frame: pd.DataFrame | None = None) -> DartsResponse:
    try:
        response = _execute_request(request, frame)
    except (ImportError, ModuleNotFoundError) as exc:
        response = DartsResponse(
            run_id=request.run_id,
            status="FAILED",
            failure_class=FailureClass.DEPENDENCY_MISSING,
            message=str(exc),
        )
    except ValueError as exc:
        response = DartsResponse(
            run_id=request.run_id,
            status="FAILED",
            failure_class=FailureClass.INVALID_REQUEST,
            message=str(exc),
        )
    except Exception as exc:
        response = DartsResponse(
            run_id=request.run_id,
            status="FAILED",
            failure_class=FailureClass.FIT_FAILED,
            message=f"{type(exc).__name__}: {exc}",
        )
    try:
        _persist_bundle(request, response)
    except Exception as exc:
        return DartsResponse(
            run_id=request.run_id,
            status="FAILED",
            failure_class=FailureClass.ARTIFACT_FAILED,
            message=f"{type(exc).__name__}: {exc}",
            metadata={"prior_status": response.status},
        )
    return response


def write_response(response: DartsResponse, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(response.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

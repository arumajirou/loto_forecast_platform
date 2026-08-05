from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .discovery import discover_models
from .executor import execute_fit_predict
from .protocol import DartsRequest, DartsResponse, FailureClass


def run_request(request: DartsRequest, *, frame: pd.DataFrame | None = None) -> DartsResponse:
    try:
        if request.mode == "discover":
            return DartsResponse(
                run_id=request.run_id,
                status="SUCCEEDED",
                model_inventory=discover_models(),
                metadata={"static_public_export_count": 58, "runtime": request.runtime},
            )
        if frame is None:
            raise ValueError("fit_predict requires an input frame")
        predictions, ledger, metadata = execute_fit_predict(request, frame)
        return DartsResponse(
            run_id=request.run_id,
            status="SUCCEEDED",
            predictions=predictions,
            argument_ledger=ledger,
            metadata=metadata,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        return DartsResponse(
            run_id=request.run_id,
            status="FAILED",
            failure_class=FailureClass.DEPENDENCY_MISSING,
            message=str(exc),
        )
    except ValueError as exc:
        return DartsResponse(
            run_id=request.run_id,
            status="FAILED",
            failure_class=FailureClass.INVALID_REQUEST,
            message=str(exc),
        )
    except Exception as exc:
        return DartsResponse(
            run_id=request.run_id,
            status="FAILED",
            failure_class=FailureClass.FIT_FAILED,
            message=f"{type(exc).__name__}: {exc}",
        )


def write_response(response: DartsResponse, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(response.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

from __future__ import annotations

import json
from pathlib import Path

from .contracts import (
    UPSTREAM_REPOSITORY,
    UPSTREAM_REVISION,
    GameGeometry,
    Operation,
    ProviderRequest,
    ProviderResponse,
    ProviderStatus,
    SourcePolicy,
    SplitContract,
)
from .data import (
    atomic_write_json,
    discover_models,
    materialize_training_bundle,
    validate_frame,
)
from .runtime import fit_save, load_predict, verify_prediction_files


def execute_request(request: ProviderRequest) -> ProviderResponse:
    if request.operation == Operation.DISCOVER:
        inventory = discover_models(request.source_root)
        request.output_dir.mkdir(parents=True, exist_ok=True)
        path = request.output_dir / "model_inventory.json"
        atomic_write_json(
            path,
            {
                "repository": UPSTREAM_REPOSITORY,
                "revision": UPSTREAM_REVISION,
                "count": len(inventory),
                "models": inventory,
            },
        )
        return ProviderResponse(
            status=ProviderStatus.PASS,
            operation=request.operation,
            model_name="*",
            artifacts={"model_inventory": str(path)},
            evidence={"model_count": len(inventory)},
        )
    if request.operation == Operation.DLINEAR_FIT_SAVE:
        return fit_save(request)
    if request.operation == Operation.DLINEAR_LOAD_PREDICT:
        return load_predict(request)
    assert request.before_prediction_path is not None
    assert request.after_prediction_path is not None
    verification = verify_prediction_files(
        request.before_prediction_path,
        request.after_prediction_path,
        rtol=request.rtol,
        atol=request.atol,
    )
    request.output_dir.mkdir(parents=True, exist_ok=True)
    path = request.output_dir / "roundtrip_verification.json"
    atomic_write_json(path, verification)
    status = ProviderStatus.PASS if verification["status"] == "PASS" else ProviderStatus.FAILED
    return ProviderResponse(
        status=status,
        operation=request.operation,
        model_name=request.model_name,
        artifacts={"verification": str(path)},
        evidence=verification,
        errors=[] if status == ProviderStatus.PASS else ["roundtrip mismatch"],
    )


def execute_request_file(request_path: Path, response_path: Path) -> int:
    try:
        request = ProviderRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
        response = execute_request(request)
    except Exception as exc:
        operation = Operation.DISCOVER
        model_name = "unknown"
        try:
            raw = json.loads(request_path.read_text(encoding="utf-8"))
            operation = Operation(str(raw.get("operation", "discover")))
            model_name = str(raw.get("model_name", model_name))
        except Exception:
            pass
        response = ProviderResponse(
            status=ProviderStatus.FAILED,
            operation=operation,
            model_name=model_name,
            errors=[f"{type(exc).__name__}: {exc}"],
        )
    atomic_write_json(response_path, response.model_dump(mode="json"))
    return 0 if response.status == ProviderStatus.PASS else 2


__all__ = [
    "GameGeometry",
    "Operation",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderStatus",
    "SourcePolicy",
    "SplitContract",
    "discover_models",
    "execute_request",
    "execute_request_file",
    "materialize_training_bundle",
    "validate_frame",
    "verify_prediction_files",
]

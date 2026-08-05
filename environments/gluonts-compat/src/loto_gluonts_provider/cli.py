from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from . import GLUONTS_VERSION, LANE, PROVIDER_STATUS, TORCH_CONSTRAINT
from .artifacts import atomic_write_json
from .discovery import discover_distributions, discover_models, runtime_versions
from .protocol import (
    EnvironmentLane,
    GluonTSProviderRequest,
    GluonTSProviderResponse,
    ProviderOperation,
    ProviderStatus,
    protocol_schema_sha256,
)


def identity_payload() -> dict[str, Any]:
    """Return declared and observed provider identity without importing GluonTS."""

    return {
        "lane": LANE,
        "declared_gluonts_version": GLUONTS_VERSION,
        "torch_constraint": TORCH_CONSTRAINT,
        "declared_status": PROVIDER_STATUS,
        "protocol_schema_sha256": protocol_schema_sha256(),
        "runtime_versions": runtime_versions(),
    }


def _response(
    request: GluonTSProviderRequest,
    status: ProviderStatus,
    metadata: dict[str, Any] | None = None,
    errors: list[str] | None = None,
) -> GluonTSProviderResponse:
    return GluonTSProviderResponse(
        request_id=request.request_id,
        run_id=request.run_id,
        lane=request.lane,
        status=status,
        metadata=metadata or {},
        errors=errors or [],
    )


def execute_request(request: GluonTSProviderRequest) -> GluonTSProviderResponse:
    """Execute one protocol operation with fail-closed phase boundaries."""

    if request.lane.value != LANE:
        return _response(
            request,
            ProviderStatus.FAILED,
            errors=[f"request lane {request.lane.value!r} does not match provider lane {LANE!r}"],
        )

    base_metadata = {
        "provider_identity": identity_payload(),
        "operation": request.operation.value,
        "phase": "P2_PROVIDER_PROTOCOL",
    }
    if request.operation is ProviderOperation.MODEL_DISCOVERY:
        discovery = discover_models()
        status = (
            ProviderStatus.PARTIALLY_VERIFIED
            if discovery["module_imported"]
            else ProviderStatus.EXECUTION_PENDING
        )
        return _response(request, status, {**base_metadata, "model_discovery": discovery})

    if request.operation is ProviderOperation.DISTRIBUTION_DISCOVERY:
        discovery = discover_distributions()
        status = (
            ProviderStatus.PARTIALLY_VERIFIED
            if discovery["module_imported"]
            else ProviderStatus.EXECUTION_PENDING
        )
        return _response(
            request,
            status,
            {**base_metadata, "distribution_discovery": discovery},
        )

    if request.operation is ProviderOperation.RUNTIME_CERTIFY:
        versions = runtime_versions()
        status = (
            ProviderStatus.PARTIALLY_VERIFIED
            if versions["gluonts"] is not None
            else ProviderStatus.EXECUTION_PENDING
        )
        return _response(
            request,
            status,
            {
                **base_metadata,
                "runtime_versions": versions,
                "certification_scope": "IMPORT_AND_VERSION_ONLY",
                "fit_predict_certified": False,
                "device_certified": False,
            },
        )

    return _response(
        request,
        ProviderStatus.EXECUTION_PENDING,
        {
            **base_metadata,
            "reason": "operation is declared by P2 but implemented in a later phase",
            "runtime_execution_performed": False,
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Isolated GluonTS provider")
    parser.add_argument("--identity", action="store_true")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--response", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate one JSON request and atomically persist one JSON response."""

    args = build_parser().parse_args(argv)
    if args.identity:
        print(json.dumps(identity_payload(), ensure_ascii=False, sort_keys=True))
        return 0
    if args.request is None or args.response is None:
        raise SystemExit("--request and --response are required unless --identity is used")

    request: GluonTSProviderRequest | None = None
    try:
        request = GluonTSProviderRequest.model_validate_json(args.request.read_text("utf-8"))
        response = execute_request(request)
    except Exception as exc:
        if request is None:
            try:
                raw = json.loads(args.request.read_text("utf-8"))
            except Exception:
                raw = {}
            try:
                lane = EnvironmentLane(raw.get("lane", LANE))
            except ValueError:
                lane = EnvironmentLane(LANE)
            request_id = str(raw.get("request_id", "invalid-request"))
            run_id = str(raw.get("run_id", "invalid-run"))
        else:
            lane = request.lane
            request_id = request.request_id
            run_id = request.run_id
        response = GluonTSProviderResponse(
            request_id=request_id,
            run_id=run_id,
            lane=lane,
            status=ProviderStatus.FAILED,
            errors=[f"{type(exc).__name__}: {exc}"],
        )

    response_sha256 = atomic_write_json(args.response, response.model_dump(mode="json"))
    print(
        json.dumps(
            {
                "request_id": response.request_id,
                "run_id": response.run_id,
                "status": response.status.value,
                "response_path": str(args.response),
                "response_sha256": response_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 1 if response.status is ProviderStatus.FAILED else 0

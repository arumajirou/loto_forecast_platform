from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from .p6_contract import (
    FailureCategory,
    P6CheckState,
    P6Operation,
    P6ProviderRequest,
    P6ProviderResponse,
    P6StageEvidence,
    P6Status,
    atomic_write_json,
)
from .p6_registry import registry_payload
from .p6_runtime import execute_stage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GluonTS P6 all-model provider")
    parser.add_argument("--registry", action="store_true")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--response", type=Path)
    return parser


def _invalid_response(raw: dict[str, object], error: str) -> P6ProviderResponse:
    lane = raw.get("lane") if raw.get("lane") in {"compat", "latest"} else "compat"
    operation_raw = raw.get("operation")
    operation = (
        P6Operation.LOAD_PREDICT
        if operation_raw == P6Operation.LOAD_PREDICT.value
        else P6Operation.FIT_SERIALIZE
    )
    model_class = str(raw.get("model_class", "invalid-model"))
    prediction_length = int(raw.get("prediction_length", 1) or 1)
    required = (
        (
            "registry",
            "version",
            "manifest",
            "artifact_integrity",
            "process_restart",
            "deserialize",
            "dataset",
            "predict",
            "shape",
            "finite",
            "device",
            "identity",
        )
        if operation is P6Operation.LOAD_PREDICT
        else (
            "registry",
            "version",
            "import",
            "signature",
            "resource_policy",
            "constructor",
            "dataset",
            "fit",
            "predict",
            "shape",
            "finite",
            "device",
            "serialize",
            "artifact_integrity",
        )
    )
    evidence = P6StageEvidence(
        lane=lane,
        operation=operation,
        model_class=model_class,
        distribution_output="UNRESOLVED",
        status=P6Status.FAILED,
        process_id=max(1, os.getpid()),
        prediction_length=max(1, prediction_length),
        expected_shape=[max(1, prediction_length)],
        failure_category=FailureCategory.UNKNOWN,
        checks={name: P6CheckState.NOT_RUN for name in required},
        errors=[error],
    )
    return P6ProviderResponse(
        request_id=str(raw.get("request_id", "invalid-request")),
        run_id=str(raw.get("run_id", "invalid-run")),
        lane=lane,
        status=P6Status.FAILED,
        evidence=evidence,
        errors=[error],
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.registry:
        print(json.dumps(registry_payload(), ensure_ascii=False, sort_keys=True))
        return 0
    if args.request is None or args.response is None:
        raise SystemExit("--request and --response are required unless --registry is used")

    raw: dict[str, object] = {}
    try:
        raw = json.loads(args.request.read_text("utf-8"))
        request = P6ProviderRequest.model_validate(raw)
        evidence = execute_stage(request)
        response = P6ProviderResponse(
            request_id=request.request_id,
            run_id=request.run_id,
            lane=request.lane,
            status=evidence.status,
            evidence=evidence,
            errors=list(evidence.errors),
        )
    except Exception as exc:
        response = _invalid_response(raw, f"{type(exc).__name__}: {exc}")

    digest = atomic_write_json(args.response, response.model_dump(mode="json"))
    print(
        json.dumps(
            {
                "request_id": response.request_id,
                "run_id": response.run_id,
                "status": response.status.value,
                "response_sha256": digest,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if response.status is P6Status.VERIFIED:
        return 0
    if response.status is P6Status.BLOCKED:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

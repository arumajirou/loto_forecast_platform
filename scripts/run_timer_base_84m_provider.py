from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.adapters.timer_base_84m.provider import TimerBase84MProvider, TimerProviderError

ENVIRONMENT = ROOT / "environments" / "timer-base-84m-supported-py310"
REVIEW = ROOT / "audit" / "tsfm-runtime" / "timer-base-84m" / "remote-code-review.json"
_OPERATIONS_WITH_REQUEST = frozenset({"validate_request", "predict"})
_ALLOWED_ENVELOPE_FIELDS = frozenset({"operation", "request"})


def _reject_non_json_constant(value: str) -> None:
    raise ValueError(f"non-JSON numeric constant is forbidden: {value}")


def _request_json(payload: dict[str, Any], operation: str) -> str:
    unknown = frozenset(payload) - _ALLOWED_ENVELOPE_FIELDS
    if unknown:
        raise ValueError(f"unknown command fields: {sorted(unknown)}")
    request_payload = payload.get("request")
    if operation in _OPERATIONS_WITH_REQUEST:
        if not isinstance(request_payload, dict):
            raise ValueError(f"operation {operation} requires a request object")
        return json.dumps(request_payload, separators=(",", ":"), allow_nan=False)
    if request_payload is not None:
        raise ValueError(f"operation {operation} must not include a request object")
    return ""


def run(payload: dict[str, Any]) -> dict[str, Any]:
    provider = TimerBase84MProvider(ENVIRONMENT, REVIEW)
    operation = payload.get("operation")
    if not isinstance(operation, str):
        raise ValueError("operation must be a string")
    request_json = _request_json(payload, operation)
    try:
        if operation == "identity":
            return {"status": "IDENTITY", "identity": provider.identity()}
        if operation == "validate_request":
            request = provider.validate_request_json(request_json)
            if request.operation != operation:
                raise ValueError("outer operation and request operation mismatch")
            return {"status": "VALIDATED", "request": request.model_dump(mode="json")}
        if operation == "validate_environment":
            return {"status": "ENVIRONMENT_VALIDATED", **provider.validate_environment()}
        if operation == "resolve_snapshot_manifest":
            return {"status": "SNAPSHOT_MANIFEST_VALIDATED", **provider.resolve_snapshot_manifest()}
        if operation == "inspect_properties":
            return {"status": "EXECUTION_PENDING", "properties": provider.inspect_properties()}
        if operation == "load":
            provider.load()
        if operation == "predict":
            request = provider.validate_request_json(request_json)
            if request.operation != operation:
                raise ValueError("outer operation and request operation mismatch")
            provider.predict(request)
        raise TimerProviderError("RUNTIME_NOT_CERTIFIED", f"unsupported operation: {operation}")
    finally:
        provider.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Timer Base 84M PR-A fail-closed provider")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = json.loads(
            args.request.read_text(encoding="utf-8"),
            parse_constant=_reject_non_json_constant,
        )
        if not isinstance(payload, dict):
            raise ValueError("command must be a JSON object")
        response = run(payload)
    except TimerProviderError as exc:
        response = {"status": exc.status, "message": str(exc)}
    except Exception as exc:
        response = {
            "status": "REQUEST_INVALID",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    args.response.parent.mkdir(parents=True, exist_ok=True)
    args.response.write_text(
        json.dumps(response, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

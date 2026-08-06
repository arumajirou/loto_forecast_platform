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


def run(payload: dict[str, Any]) -> dict[str, Any]:
    provider = TimerBase84MProvider(ENVIRONMENT, REVIEW)
    operation = payload.get("operation")
    try:
        if operation == "identity":
            return {"status": "IDENTITY", "identity": provider.identity()}
        if operation == "validate_request":
            request = provider.validate_request(payload["request"])
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
            request = provider.validate_request(payload["request"])
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
        payload = json.loads(args.request.read_text(encoding="utf-8"))
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

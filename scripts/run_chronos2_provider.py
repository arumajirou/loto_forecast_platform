#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.chronos2_campaign.provider import execute_request  # noqa: E402


def _write_response(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run_reference_reload_child(
    request_path: Path,
    response_path: Path,
) -> int:
    with tempfile.TemporaryDirectory(prefix="chronos2-reload-") as temp_dir:
        child_response = Path(temp_dir) / "response.json"
        environment = {**os.environ, "CHRONOS2_REFERENCE_RELOAD_CHILD": "1"}
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--request",
                str(request_path),
                "--response",
                str(child_response),
            ],
            check=False,
            env=environment,
            capture_output=True,
            text=True,
        )
        if not child_response.is_file():
            _write_response(
                response_path,
                {
                    "schema_version": 2,
                    "status": "ERROR",
                    "run_id": "unknown",
                    "operation": "reference_reload",
                    "error": {
                        "type": "ReloadSubprocessError",
                        "message": "reload child produced no response",
                        "returncode": completed.returncode,
                        "stderr": completed.stderr,
                    },
                },
            )
            return 2
        payload = json.loads(child_response.read_text(encoding="utf-8"))
        runtime = payload.get("runtime_evidence")
        if isinstance(runtime, dict):
            runtime["reload_process_distinct"] = runtime.get("provider_pid") != os.getpid()
            runtime["parent_pid"] = os.getpid()
        _write_response(response_path, payload)
        return 0 if payload.get("status") == "OK" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Chronos-2 provider contract v2")
    parser.add_argument("--request", required=True)
    parser.add_argument("--response", required=True)
    args = parser.parse_args()

    request_path = Path(args.request).expanduser().resolve()
    response_path = Path(args.response).expanduser().resolve()
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    is_reload = payload.get("operation") == "reference_reload"
    if is_reload and os.getenv("CHRONOS2_REFERENCE_RELOAD_CHILD") != "1":
        return _run_reference_reload_child(request_path, response_path)

    payload["parent_pid"] = payload.get("parent_pid") or os.getppid()
    response = execute_request(payload)
    _write_response(response_path, response.model_dump(mode="json"))
    return 0 if response.status == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.adapters.toto2_4m import (  # noqa: E402
    RuntimeEvidence,
    Toto2ProviderRequest,
    Toto2ProviderResponse,
    Toto2ResponseAdapter,
)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def execute(
    request_path: Path,
    *,
    native_output_path: Path | None,
    runtime_evidence_path: Path | None,
    artifact_reference_path: Path | None,
) -> Toto2ProviderResponse:
    request = Toto2ProviderRequest.model_validate(_load_json(request_path))
    if request.operation.value == "identity":
        return Toto2ResponseAdapter.identity_response()
    if native_output_path is None or runtime_evidence_path is None:
        return Toto2ProviderResponse(
            status="BLOCKED",
            phase="runtime_boundary",
            message=(
                "P0-P2 validates contracts and native output only; actual Toto inference "
                "must run in the reviewed isolated Python 3.12 lane"
            ),
            model_identity=Toto2ResponseAdapter.identity_response().model_identity,
            unsupported_arguments=["in_process_root_runtime_inference"],
        )
    native_output = np.load(native_output_path, allow_pickle=False)
    runtime_evidence = RuntimeEvidence.model_validate(_load_json(runtime_evidence_path))
    artifact_reference = (
        _load_json(artifact_reference_path) if artifact_reference_path is not None else {}
    )
    return Toto2ResponseAdapter.from_native(
        request,
        native_output,
        runtime_evidence=runtime_evidence,
        artifact_reference=artifact_reference,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Toto 2.0 4M isolated provider contract runner")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--native-output", type=Path)
    parser.add_argument("--runtime-evidence", type=Path)
    parser.add_argument("--artifact-reference", type=Path)
    args = parser.parse_args()

    try:
        response = execute(
            args.request,
            native_output_path=args.native_output,
            runtime_evidence_path=args.runtime_evidence,
            artifact_reference_path=args.artifact_reference,
        )
        _write_json_atomic(args.response, response.model_dump(mode="json"))
        return 0 if response.status == "OK" else 2
    except (OSError, ValueError, ValidationError) as exc:
        response = Toto2ProviderResponse(
            status="ERROR",
            phase="contract_validation",
            message=f"{type(exc).__name__}: {exc}",
        )
        _write_json_atomic(args.response, response.model_dump(mode="json"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

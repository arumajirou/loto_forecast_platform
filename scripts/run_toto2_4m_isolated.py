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

from loto.adapters.toto2_4m.contracts import Toto2ProviderRequest  # noqa: E402
from loto.toto2_campaign.isolated_runtime import execute_isolated_runtime  # noqa: E402
from loto.toto2_campaign.runtime_executor import (  # noqa: E402
    RuntimeDependencyError,
    RuntimeExecutionError,
    SnapshotIntegrityError,
)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _atomic_save_numpy(path: Path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        np.save(handle, array, allow_pickle=False)
    temporary.replace(path)


def _load_request(path: Path) -> Toto2ProviderRequest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("request JSON root must be an object")
    return Toto2ProviderRequest.model_validate(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Toto 2.0 4M in its isolated lane")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--ready", type=Path)
    parser.add_argument("--start", type=Path)
    parser.add_argument("--handshake-timeout-seconds", type=float, default=120.0)
    args = parser.parse_args()

    args.run_dir.mkdir(parents=True, exist_ok=False)
    try:
        request = _load_request(args.request)
        result = execute_isolated_runtime(
            request,
            snapshot_path=args.snapshot,
            ready_path=args.ready,
            start_path=args.start,
            handshake_timeout_seconds=args.handshake_timeout_seconds,
        )
        native_output_path = args.run_dir / "native_output.npy"
        runtime_evidence_path = args.run_dir / "runtime_evidence.internal.json"
        artifact_reference_path = args.run_dir / "artifact_reference.json"
        _atomic_save_numpy(native_output_path, result.native_output)
        _atomic_write_json(
            runtime_evidence_path,
            result.runtime_evidence.model_dump(mode="json"),
        )
        _atomic_write_json(artifact_reference_path, result.artifact_reference)
        _atomic_write_json(
            args.run_dir / "executor_result.json",
            {
                "status": "PASS",
                "provider_pid": os.getpid(),
                "native_output_path": str(native_output_path),
                "runtime_evidence_path": str(runtime_evidence_path),
                "artifact_reference_path": str(artifact_reference_path),
            },
        )
        return 0
    except (
        OSError,
        ValueError,
        ValidationError,
        RuntimeDependencyError,
        RuntimeExecutionError,
        SnapshotIntegrityError,
    ) as exc:
        _atomic_write_json(
            args.run_dir / "executor_result.json",
            {
                "status": "FAIL",
                "provider_pid": os.getpid(),
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from loto.adapters.toto2_4m.contracts import RuntimeEvidence, Toto2ProviderRequest
from loto.toto2_campaign.runtime_executor import forecast_prepared, prepare_runtime


@dataclass(frozen=True)
class InternalRuntimeResult:
    native_output: np.ndarray
    runtime_evidence: RuntimeEvidence
    artifact_reference: dict[str, Any]


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _wait_for_start(path: Path, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"runtime start handshake timed out after {timeout_seconds:.1f} seconds"
            )
        time.sleep(0.05)


def execute_isolated_runtime(
    request: Toto2ProviderRequest,
    *,
    snapshot_path: Path,
    ready_path: Path | None = None,
    start_path: Path | None = None,
    handshake_timeout_seconds: float = 120.0,
) -> InternalRuntimeResult:
    prepared = prepare_runtime(request, snapshot_path)
    if ready_path is not None:
        _write_json_atomic(
            ready_path,
            {
                "provider_pid": os.getpid(),
                "requested_device": request.device,
                "model_device": prepared.model_device,
                "snapshot": prepared.snapshot,
            },
        )
    if start_path is not None:
        _wait_for_start(start_path, handshake_timeout_seconds)
    native_output, evidence, artifact_reference = forecast_prepared(request, prepared)
    return InternalRuntimeResult(native_output, evidence, artifact_reference)

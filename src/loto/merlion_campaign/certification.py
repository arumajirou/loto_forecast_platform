from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from loto.adapters.merlion.adapter import MerlionProviderAdapter
from loto.merlion_campaign.protocol import Operation, ProviderRequest, ProviderResponse


@dataclass(frozen=True)
class CertificationResult:
    status: str
    train_process_id: int
    load_process_id: int
    prediction_match: bool
    report_sha256: str
    report: dict[str, object]


def _response_prediction(response: ProviderResponse) -> np.ndarray:
    if response.prediction is None:
        raise ValueError("provider response has no prediction")
    values = np.asarray(response.prediction.values, dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("provider prediction is not finite")
    return values


def certify_core_model(
    command: Sequence[str],
    request: ProviderRequest,
    work_root: Path,
    *,
    timeout_seconds: float = 120.0,
) -> CertificationResult:
    if request.operation is not Operation.TRAIN_SAVE:
        raise ValueError("certification input must be a train_save request")
    adapter = MerlionProviderAdapter(command, timeout_seconds=timeout_seconds)
    train_response = adapter.run(request, work_root)
    manifest_sha = train_response.evidence.get("model_manifest_sha256")
    if not isinstance(manifest_sha, str):
        raise ValueError("train response omitted model manifest hash")
    load_request = request.model_copy(
        update={
            "request_id": f"{request.request_id}-reload",
            "operation": Operation.LOAD_PREDICT,
            "series": None,
            "expected_manifest_sha256": manifest_sha,
        }
    )
    load_response = adapter.run(load_request, work_root)
    train_values = _response_prediction(train_response)
    load_values = _response_prediction(load_response)
    prediction_match = bool(np.allclose(train_values, load_values, rtol=1e-8, atol=1e-8))
    distinct_processes = train_response.process_id != load_response.process_id
    status = "RUNTIME_VERIFIED" if prediction_match and distinct_processes else "FAILED"
    report: dict[str, object] = {
        "schema_version": "merlion-core-certification-v1",
        "status": status,
        "model_name": request.model_name,
        "train_process_id": train_response.process_id,
        "load_process_id": load_response.process_id,
        "distinct_processes": distinct_processes,
        "prediction_match": prediction_match,
        "model_manifest_sha256": manifest_sha,
        "device": "cpu",
        "gpu_not_applicable": True,
        "cpu_fallback": False,
    }
    canonical = json.dumps(report, separators=(",", ":"), sort_keys=True).encode("utf-8")
    report_sha = hashlib.sha256(canonical).hexdigest()
    report["report_sha256"] = report_sha
    return CertificationResult(
        status=status,
        train_process_id=train_response.process_id,
        load_process_id=load_response.process_id,
        prediction_match=prediction_match,
        report_sha256=report_sha,
        report=report,
    )

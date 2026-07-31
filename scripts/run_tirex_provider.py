from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

REPO_ID = "NX-AI/TiRex-2"
REVISION = "05e5b26db52bfb256f1ae1bdf785589850482de3"


def _load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot(
    repo_id: str, revision: str | None, local_files_only: bool, snapshot: str | None
) -> Path:
    if snapshot:
        snapshot_path = Path(snapshot)
        if not snapshot_path.exists():
            raise FileNotFoundError(f"snapshot_path does not exist: {snapshot_path}")
        return snapshot_path
    from huggingface_hub import snapshot_download

    return Path(
        snapshot_download(
            repo_id=repo_id,
            revision=revision,
            local_files_only=local_files_only,
            allow_patterns=[
                "*.yaml",
                "*.yml",
                "*.ckpt",
                "*.json",
                "*.safetensors",
                "*.bin",
                "*.py",
                "LICENSE",
                "NOTICE",
                "README.md",
            ],
        )
    )


def run_provider(request: dict[str, Any]) -> dict[str, Any]:
    from tirex2 import TimeseriesType, load_model

    repo_id = str(request.get("repo_id", REPO_ID))
    revision = str(request.get("revision") or REVISION)
    snapshot_path = _snapshot(
        repo_id,
        revision,
        bool(request.get("local_files_only", True)),
        request.get("snapshot_path"),
    )
    config_path = snapshot_path / "model-config.yaml"
    weights = (
        sorted(snapshot_path.glob("*.ckpt"))
        + sorted(snapshot_path.glob("*.safetensors"))
        + sorted(snapshot_path.glob("*.bin"))
    )
    if not config_path.exists():
        return {
            "status": "PARTIAL_SNAPSHOT",
            "message": f"model-config.yaml missing in {snapshot_path}",
        }
    if not weights:
        return {
            "status": "MODEL_WEIGHTS_MISSING",
            "message": f"no model weights found in {snapshot_path}",
        }

    requested_device = str(request.get("device", "cpu"))
    cuda_available = torch.cuda.is_available()
    execution_device = "cuda" if requested_device == "cuda" and cuda_available else "cpu"
    if execution_device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    model = load_model(
        repo_id,
        device=execution_device,
        hf_kwargs={"revision": revision, "local_files_only": True},
    )
    history = pd.DataFrame(request["history"])
    context = torch.tensor(
        history[[f"n{position}" for position in range(1, 8)]].to_numpy(dtype=np.float32).T,
        dtype=torch.float32,
    )
    timeseries = TimeseriesType(target=context, past_covariates=None, future_covariates=None)
    horizon = int(request.get("prediction_length", 1))
    forecast = np.asarray(
        model.forecast([timeseries], prediction_length=horizon, output_type="numpy")[0], dtype=float
    )
    if forecast.shape[:2] != (7, 9) or forecast.shape[2] < horizon:
        return {
            "status": "INVALID_PREDICTION",
            "message": f"unexpected TiRex forecast shape: {forecast.shape}",
        }
    predictions = forecast[:, 4, 0]
    gpu_used = execution_device == "cuda"
    return {
        "status": "OK",
        "schema_version": 1,
        "provider_version": 1,
        "repo_id": repo_id,
        "snapshot_path": str(snapshot_path),
        "predictions": predictions.astype(float).tolist(),
        "prediction_shape": list(predictions.shape),
        "finite": bool(np.isfinite(predictions).all()),
        "properties": {
            "library": "tirex2",
            "package": "tirex-2",
            "package_version": importlib.metadata.version("tirex-2"),
            "license": "apache-2.0",
            "backend": "torch",
            "context_length": int(context.shape[1]),
            "max_context_length": 2048,
            "prediction_length": horizon,
            "quantile_support": True,
            "quantile_shape": list(forecast.shape),
            "weight_files": [str(path) for path in weights],
            "weight_sha256": {str(path): _sha256(path) for path in weights},
            "config_sha256": _sha256(config_path),
            "snapshot_complete": True,
        },
        "gpu_evidence": {
            "requested_device": requested_device,
            "execution_device": execution_device,
            "cuda_available": cuda_available,
            "gpu_requested": requested_device == "cuda",
            "gpu_used": gpu_used,
            "gpu_certification": "OBSERVED" if gpu_used else "NOT_CERTIFIED",
            "resource_certification": "GPU_PASS" if gpu_used else "CPU_ONLY_PASS",
            "cpu_fallback": requested_device == "cuda" and not gpu_used,
            "fallback_reason": None
            if execution_device == requested_device
            else "cuda_unavailable_or_not_selected",
            "peak_vram_bytes": int(torch.cuda.max_memory_allocated()) if gpu_used else 0,
            "gpu_pid": os.getpid() if gpu_used else None,
        },
        "artifact_reference": {
            "repo_id": repo_id,
            "revision": revision,
            "snapshot_path": str(snapshot_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TiRex-2 provider in an isolated env")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path)
    args = parser.parse_args()
    try:
        response = run_provider(_load_payload(args.request))
    except Exception as exc:
        response = {"status": "ERROR", "error_type": type(exc).__name__, "message": str(exc)}
    _write_payload(args.response, response)


if __name__ == "__main__":
    main()

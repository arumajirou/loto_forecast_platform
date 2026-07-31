from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ID = "google/timesfm-2.5-200m-pytorch"


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


def run_provider(request: dict[str, Any]) -> dict[str, Any]:
    import timesfm
    import torch
    from huggingface_hub import snapshot_download

    repo_id = request.get("repo_id", REPO_ID)
    snapshot = request.get("snapshot_path")
    if snapshot:
        snapshot_path = Path(snapshot)
        if not snapshot_path.exists():
            raise FileNotFoundError(f"snapshot_path does not exist: {snapshot_path}")
    else:
        snapshot_path = Path(
            snapshot_download(
                repo_id=repo_id,
                revision=request.get("revision"),
                local_files_only=bool(request.get("local_files_only", True)),
                allow_patterns=["*.json", "*.safetensors", "README.md"],
            )
        )

    requested_device = str(request.get("device", "cpu"))
    cuda_available = torch.cuda.is_available()
    device = "cuda" if requested_device == "cuda" and cuda_available else "cpu"
    torch.set_float32_matmul_precision("high")
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
        snapshot_path,
        local_files_only=True,
        torch_compile=False,
    )
    model.compile(
        timesfm.ForecastConfig(
            max_context=1024,
            max_horizon=256,
            normalize_inputs=True,
            use_continuous_quantile_head=True,
            force_flip_invariance=True,
            infer_is_positive=True,
            fix_quantile_crossing=True,
        )
    )
    history = pd.DataFrame(request["history"])
    inputs = [history[f"n{position}"].to_numpy(dtype=np.float32) for position in range(1, 8)]
    horizon = int(request.get("prediction_length", 1))
    point_forecast, quantile_forecast = model.forecast(horizon=horizon, inputs=inputs)
    predictions = np.asarray(point_forecast, dtype=float)[:, 0]
    weights = sorted(snapshot_path.rglob("*.safetensors"))
    config_path = snapshot_path / "config.json"
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
            "library": "timesfm",
            "license": "apache-2.0",
            "backend": "torch",
            "context_length": 1024,
            "prediction_length": horizon,
            "quantile_support": True,
            "quantile_shape": list(np.asarray(quantile_forecast).shape),
            "weight_files": [str(path) for path in weights],
            "weight_sha256": {str(path): _sha256(path) for path in weights},
            "config_sha256": _sha256(config_path) if config_path.exists() else None,
        },
        "gpu_evidence": {
            "cuda_available": cuda_available,
            "requested_device": requested_device,
            "execution_device": device,
            "gpu_requested": requested_device == "cuda",
            "gpu_used": device == "cuda",
            "gpu_certification": "NOT_CERTIFIED" if device == "cpu" else "OBSERVED",
            "fallback_reason": (
                None if device == requested_device else "cuda_unavailable_or_not_selected"
            ),
            "vram_peak_bytes": torch.cuda.max_memory_allocated() if device == "cuda" else 0,
        },
        "artifact_reference": {
            "repo_id": repo_id,
            "snapshot_path": str(snapshot_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TimesFM provider in an isolated env")
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

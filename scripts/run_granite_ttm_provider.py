from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ID = "ibm-granite/granite-timeseries-ttm-r2"


def _load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _prediction_to_positions(output: Any) -> list[float]:
    prediction = getattr(output, "prediction_outputs", None)
    if prediction is None:
        prediction = getattr(output, "last_hidden_state", None)
    if prediction is None:
        raise RuntimeError("Granite TTM output did not expose a prediction tensor")
    array = prediction.detach().cpu().numpy()
    return array.reshape(7, -1)[:, -1].astype(float).tolist()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_provider(request: dict[str, Any]) -> dict[str, Any]:
    import torch
    from huggingface_hub import snapshot_download
    from tsfm_public import TinyTimeMixerForPrediction

    snapshot = snapshot_download(
        repo_id=request.get("repo_id", REPO_ID),
        revision=request.get("revision"),
        local_files_only=bool(request.get("local_files_only", True)),
        allow_patterns=["*.json", "*.safetensors", "*.bin", "*.py", "*.txt", "README.md"],
    )
    device = "cuda" if request.get("device") == "cuda" and torch.cuda.is_available() else "cpu"
    model = TinyTimeMixerForPrediction.from_pretrained(snapshot, local_files_only=True)
    model.to(device)
    model.eval()

    history = pd.DataFrame(request["history"])
    values = history[[f"n{i}" for i in range(1, 8)]].to_numpy(dtype=np.float32).T
    context_length = int(getattr(model.config, "context_length", values.shape[1]))
    if values.shape[1] < context_length:
        pad = np.repeat(values[:, :1], context_length - values.shape[1], axis=1)
        values = np.concatenate([pad, values], axis=1)
    else:
        values = values[:, -context_length:]
    context = torch.tensor(values, dtype=torch.float32, device=device).unsqueeze(-1)
    with torch.no_grad():
        output = model(past_values=context)
    weights = sorted(
        [
            path
            for pattern in ("*.safetensors", "*.bin")
            for path in Path(snapshot).rglob(pattern)
            if path.is_file()
        ]
    )
    return {
        "status": "OK",
        "schema_version": 1,
        "provider_version": 1,
        "repo_id": request.get("repo_id", REPO_ID),
        "snapshot_path": str(snapshot),
        "device": device,
        "predictions": _prediction_to_positions(output),
        "shape": [7],
        "finite": True,
        "properties": {
            "license": "apache-2.0",
            "library": "granite-tsfm",
            "weight_files": [str(path) for path in weights],
            "weight_sha256": {str(path): _sha256(path) for path in weights},
            "config_sha256": _sha256(Path(snapshot) / "config.json")
            if (Path(snapshot) / "config.json").exists()
            else None,
        },
        "gpu_evidence": {
            "cuda_available": torch.cuda.is_available(),
            "device": device,
            "vram_peak_bytes": torch.cuda.max_memory_allocated() if device == "cuda" else 0,
        },
        "artifact_reference": {
            "repo_id": request.get("repo_id", REPO_ID),
            "snapshot_path": str(snapshot),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Granite TTM provider in an isolated env")
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

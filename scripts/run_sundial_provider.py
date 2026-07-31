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

REPO_ID = "thuml/sundial-base-128m"
REVISION = "3212e42564493f520593e5414af4367fc4b49226"


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


def _snapshot(repo_id: str, revision: str | None, local_files_only: bool, snapshot: str | None) -> Path:
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
            allow_patterns=["*.json", "*.safetensors", "*.bin", "*.py", "*.txt", "README.md", "LICENSE*"],
        )
    )


def run_provider(request: dict[str, Any]) -> dict[str, Any]:
    requested_device = str(request.get("device", "cpu"))
    if requested_device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    import torch
    from transformers import AutoModelForCausalLM

    repo_id = str(request.get("repo_id", REPO_ID))
    revision = str(request.get("revision") or REVISION)
    snapshot_path = _snapshot(
        repo_id,
        revision,
        bool(request.get("local_files_only", True)),
        request.get("snapshot_path"),
    )
    config_path = snapshot_path / "config.json"
    weights = sorted(snapshot_path.glob("*.safetensors")) + sorted(snapshot_path.glob("*.bin"))
    remote_code = sorted(snapshot_path.glob("*.py"))
    if not config_path.exists() or not remote_code:
        return {"status": "PARTIAL_SNAPSHOT", "message": f"config or remote code missing in {snapshot_path}"}
    if not weights:
        return {"status": "MODEL_WEIGHTS_MISSING", "message": f"no model weights found in {snapshot_path}"}

    cuda_available = torch.cuda.is_available()
    execution_device = "cuda" if requested_device == "cuda" and cuda_available else "cpu"
    if execution_device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    model = AutoModelForCausalLM.from_pretrained(
        repo_id,
        revision=revision,
        trust_remote_code=True,
        local_files_only=True,
        torch_dtype=torch.float32,
        device_map=None,
    ).to(execution_device)
    model.eval()
    history = pd.DataFrame(request["history"])
    context = torch.tensor(
        history[[f"n{position}" for position in range(1, 8)]].to_numpy(dtype=np.float32).T,
        dtype=torch.float32,
        device=execution_device,
    )
    horizon = int(request.get("prediction_length", 1))
    seed = int(request.get("seed", 42))
    np.random.seed(seed)
    torch.manual_seed(seed)
    if execution_device == "cuda":
        torch.cuda.manual_seed_all(seed)
    with torch.no_grad():
        samples = model.generate(
            inputs=context,
            max_length=context.shape[1] + horizon,
            num_samples=3,
            revin=True,
        )
    predictions = samples.median(dim=1)[0][:, 0].detach().cpu().numpy().astype(float)
    gpu_used = execution_device == "cuda"
    return {
        "status": "OK",
        "schema_version": 1,
        "provider_version": 1,
        "repo_id": repo_id,
        "snapshot_path": str(snapshot_path),
        "predictions": predictions.tolist(),
        "prediction_shape": list(predictions.shape),
        "finite": bool(np.isfinite(predictions).all()),
        "properties": {
            "library": "transformers",
            "package": "transformers",
            "transformers_version": importlib.metadata.version("transformers"),
            "torch_version": torch.__version__,
            "license": "apache-2.0",
            "backend": "torch",
            "trust_remote_code": True,
            "remote_code_revision": revision,
            "remote_code_sha256": {str(path): _sha256(path) for path in remote_code},
            "context_length": int(context.shape[1]),
            "prediction_length": horizon,
            "num_samples": 3,
            "random_seed": seed,
            "model_architecture": "SundialForPrediction",
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
            "fallback_reason": None if execution_device == requested_device else "cuda_unavailable_or_not_selected",
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
    parser = argparse.ArgumentParser(description="Run Sundial provider in an isolated env")
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

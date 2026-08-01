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

REPO_ID = "Salesforce/moirai-2.0-R-small"
REVISION = "30f43ff08c8494f4943ae1521e9d4e94a0fbb389"


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
            allow_patterns=["*.json", "*.safetensors", "*.bin", "*.ckpt", "README.md", "LICENSE*"],
        )
    )


def run_provider(request: dict[str, Any]) -> dict[str, Any]:
    requested_device = str(request.get("device", "cpu"))
    if requested_device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    import torch
    from gluonts.dataset.common import ListDataset
    from uni2ts.model.moirai2 import Moirai2Forecast, Moirai2Module

    repo_id = str(request.get("repo_id", REPO_ID))
    revision = str(request.get("revision") or REVISION)
    snapshot_path = _snapshot(
        repo_id,
        revision,
        bool(request.get("local_files_only", True)),
        request.get("snapshot_path"),
    )
    config_path = snapshot_path / "config.json"
    weights = (
        sorted(snapshot_path.glob("*.safetensors"))
        + sorted(snapshot_path.glob("*.bin"))
        + sorted(snapshot_path.glob("*.ckpt"))
    )
    if not config_path.exists():
        return {"status": "PARTIAL_SNAPSHOT", "message": f"config.json missing in {snapshot_path}"}
    if not weights:
        return {
            "status": "MODEL_WEIGHTS_MISSING",
            "message": f"no model weights found in {snapshot_path}",
        }

    cuda_available = torch.cuda.is_available()
    execution_device = "cuda" if requested_device == "cuda" and cuda_available else "cpu"
    if execution_device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    history = pd.DataFrame(request["history"])
    target = history[[f"n{position}" for position in range(1, 8)]].to_numpy(dtype=np.float32).T
    horizon = int(request.get("prediction_length", 1))
    context_length = min(128, target.shape[1])
    dataset = ListDataset(
        [{"start": "2020-01-01", "target": target}],
        freq="D",
        one_dim_target=False,
    )
    if snapshot_path.name != revision:
        raise RuntimeError(f"snapshot revision mismatch: {snapshot_path.name} != {revision}")

    module = Moirai2Module.from_pretrained(
        str(snapshot_path),
        local_files_only=True,
    )
    module = module.to(execution_device).eval()

    module_parameter = next(module.parameters())

    if execution_device == "cuda":
        if module_parameter.device.type != "cuda":
            raise RuntimeError(f"Moirai module is not on CUDA: {module_parameter.device}")

    model = Moirai2Forecast(
        module=module,
        prediction_length=horizon,
        context_length=context_length,
        target_dim=7,
        feat_dynamic_real_dim=0,
        past_feat_dynamic_real_dim=0,
    )

    predictor = model.create_predictor(
        batch_size=1,
        device=execution_device,
    )

    forecast = next(iter(predictor.predict(dataset)))

    if execution_device == "cuda":
        torch.cuda.synchronize()
    median = np.asarray(forecast.quantile(0.5), dtype=float)
    if median.shape != (horizon, 7):
        return {
            "status": "INVALID_PREDICTION",
            "message": f"unexpected Moirai forecast shape: {median.shape}",
        }
    predictions = median[0, :]
    gpu_used = execution_device == "cuda"
    return {
        "status": "OK",
        "schema_version": 1,
        "provider_version": 1,
        "model_id": str(request.get("model_id", "moirai-2.0-small")),
        "repo_id": repo_id,
        "revision": revision,
        "snapshot_path": str(snapshot_path),
        "predictions": predictions.astype(float).tolist(),
        "prediction_shape": list(predictions.shape),
        "finite": bool(np.isfinite(predictions).all()),
        "properties": {
            "library": "uni2ts",
            "package": "uni2ts",
            "package_version": importlib.metadata.version("uni2ts"),
            "gluonts_version": importlib.metadata.version("gluonts"),
            "torch_version": torch.__version__,
            "license": "cc-by-nc-4.0",
            "backend": "torch",
            "context_length": context_length,
            "prediction_length": horizon,
            "patch_size": "auto",
            "num_samples": 9,
            "target_dim": 7,
            "quantile_support": True,
            "quantile_shape": list(median.shape),
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
            "model_device": str(module_parameter.device),
            "peak_vram_bytes": (int(torch.cuda.max_memory_allocated()) if gpu_used else 0),
            "gpu_pid": (os.getpid() if gpu_used else None),
        },
        "artifact_reference": {
            "repo_id": repo_id,
            "revision": revision,
            "snapshot_path": str(snapshot_path),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Moirai provider in an isolated env")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path)
    args = parser.parse_args()
    try:
        response = run_provider(_load_payload(args.request))
    except Exception as exc:
        response = {"status": "ERROR", "error_type": type(exc).__name__, "message": str(exc)}
    _write_payload(args.response, response)

    return 0 if response.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())

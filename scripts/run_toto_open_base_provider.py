from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

MODEL_ID = "toto-open-base"
REPO_ID = "Datadog/Toto-Open-Base-1.0"
REVISION = "0411ceb27bdf7fc3e4892e99edc8ad08192dc3c5"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def run_provider(request: dict[str, Any]) -> dict[str, Any]:
    requested_device = str(request.get("device", "cuda"))

    if requested_device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    import torch
    from toto.data.util.dataset import MaskedTimeseries
    from toto.inference.forecaster import TotoForecaster
    from toto.model.toto import Toto

    snapshot = Path(request["snapshot_path"]).resolve()
    revision = str(request.get("revision") or REVISION)

    if snapshot.name != revision:
        raise RuntimeError(f"snapshot revision mismatch: {snapshot.name} != {revision}")

    config_path = snapshot / "config.json"
    weights_path = snapshot / "model.safetensors"

    if not config_path.is_file():
        raise FileNotFoundError(f"missing {config_path}")

    if not weights_path.is_file():
        raise FileNotFoundError(f"missing {weights_path}")

    cuda_available = torch.cuda.is_available()
    execution_device = "cuda" if requested_device == "cuda" and cuda_available else "cpu"

    if requested_device == "cuda" and execution_device != "cuda":
        raise RuntimeError("CUDA requested but unavailable")

    if execution_device == "cuda":
        torch.cuda.set_device(0)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(0)

    history = np.asarray(request["history"], dtype=np.float32)

    if history.ndim != 2 or history.shape[0] != 7:
        raise ValueError(f"history must have shape [7, context], got {history.shape}")

    context_length = int(history.shape[1])
    prediction_length = int(request.get("prediction_length", 1))
    num_samples = int(request.get("num_samples", 256))
    samples_per_batch = int(request.get("samples_per_batch", 64))

    toto = Toto.from_pretrained(str(snapshot)).to(execution_device)
    toto.eval()

    parameter = next(toto.parameters())

    series = torch.as_tensor(
        history,
        dtype=torch.float32,
        device=execution_device,
    )

    padding_mask = torch.ones_like(
        series,
        dtype=torch.bool,
    )

    id_mask = torch.zeros_like(
        series,
        dtype=torch.long,
    )

    interval_seconds = int(request.get("time_interval_seconds", 86400))

    time_interval_seconds = torch.full(
        (7,),
        interval_seconds,
        dtype=torch.long,
        device=execution_device,
    )

    timestamp_seconds = (
        torch.arange(
            context_length,
            dtype=torch.long,
            device=execution_device,
        )
        .unsqueeze(0)
        .repeat(7, 1)
        * interval_seconds
    )

    inputs = MaskedTimeseries(
        series=series,
        padding_mask=padding_mask,
        id_mask=id_mask,
        timestamp_seconds=timestamp_seconds,
        time_interval_seconds=time_interval_seconds,
    )

    forecaster = TotoForecaster(toto.model)

    with torch.inference_mode():
        forecast = forecaster.forecast(
            inputs,
            prediction_length=prediction_length,
            num_samples=num_samples,
            samples_per_batch=samples_per_batch,
            use_kv_cache=True,
        )

    if execution_device == "cuda":
        torch.cuda.synchronize(0)

    median = forecast.median
    samples = forecast.samples

    if samples is None:
        raise RuntimeError("forecast samples are missing")

    if median.shape != (1, 7, prediction_length):
        raise RuntimeError(f"unexpected median shape: {tuple(median.shape)}")

    predictions = median[0, :, 0]

    predictions_np = predictions.detach().cpu().numpy().astype(float)

    if not np.isfinite(predictions_np).all():
        raise RuntimeError("non-finite Toto predictions")

    return {
        "status": "OK",
        "schema_version": 1,
        "provider_version": 1,
        "model_id": MODEL_ID,
        "repo_id": REPO_ID,
        "revision": revision,
        "snapshot_path": str(snapshot),
        "model_class": type(toto).__name__,
        "forecaster_class": type(forecaster).__name__,
        "model_parameter_count": sum(item.numel() for item in toto.parameters()),
        "input_shape": list(history.shape),
        "prediction_length": prediction_length,
        "num_samples": num_samples,
        "samples_per_batch": samples_per_batch,
        "sample_shape": list(samples.shape),
        "median_shape": list(median.shape),
        "prediction_shape": list(predictions_np.shape),
        "predictions": predictions_np.tolist(),
        "finite": True,
        "properties": {
            "package": "toto-ts",
            "package_version": importlib.metadata.version("toto-ts"),
            "torch_version": torch.__version__,
            "context_length": context_length,
            "target_dim": 7,
            "config_sha256": _sha256(config_path),
            "weight_sha256": _sha256(weights_path),
            "weight_size_bytes": weights_path.stat().st_size,
            "license": "apache-2.0",
            "snapshot_complete": True,
        },
        "gpu_evidence": {
            "requested_device": requested_device,
            "execution_device": execution_device,
            "cuda_available": cuda_available,
            "gpu_used": execution_device == "cuda",
            "cpu_fallback": (requested_device == "cuda" and execution_device != "cuda"),
            "model_device": str(parameter.device),
            "output_device": str(median.device),
            "peak_vram_bytes": (
                int(torch.cuda.max_memory_allocated(0)) if execution_device == "cuda" else 0
            ),
            "gpu_pid": (os.getpid() if execution_device == "cuda" else None),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Toto Open Base provider")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path)
    args = parser.parse_args()

    try:
        response = run_provider(_read_json(args.request))
    except Exception as exc:
        response = {
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }

    _write_json(args.response, response)

    return 0 if response.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())

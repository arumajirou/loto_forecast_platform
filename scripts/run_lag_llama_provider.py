from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

MODEL_ID = "lag-llama"
REPO_ID = "time-series-foundation-models/Lag-Llama"
REVISION = "72dcfc29da106acfe38250a60f4ae29d1e56a3d9"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n",
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

    import pandas as pd
    import torch
    from gluonts.dataset.common import ListDataset
    from lag_llama.gluon.estimator import LagLlamaEstimator

    snapshot = Path(request["snapshot_path"]).resolve()
    revision = str(request.get("revision") or REVISION)

    if snapshot.name != revision:
        raise RuntimeError(f"snapshot revision mismatch: {snapshot.name} != {revision}")

    checkpoint_path = snapshot / "lag-llama.ckpt"

    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"missing {checkpoint_path}")

    cuda_available = torch.cuda.is_available()
    execution_device = "cuda" if requested_device == "cuda" and cuda_available else "cpu"

    if requested_device == "cuda" and execution_device != "cuda":
        raise RuntimeError("CUDA requested but unavailable")

    device = torch.device(execution_device)

    if execution_device == "cuda":
        torch.cuda.set_device(0)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(0)

    checkpoint = torch.load(
        checkpoint_path,
        map_location="cpu",
        weights_only=False,
    )

    hyper_parameters = checkpoint["hyper_parameters"]
    model_kwargs = dict(hyper_parameters["model_kwargs"])

    history = np.asarray(request["history"], dtype=np.float32)

    if history.ndim != 2 or history.shape[0] != 7:
        raise ValueError(f"history must have shape [7, context], got {history.shape}")

    prediction_length = int(request.get("prediction_length", 1))
    context_length = min(
        int(request.get("context_length", 32)),
        int(history.shape[1]),
    )
    num_samples = int(request.get("num_samples", 100))

    estimator = LagLlamaEstimator(
        prediction_length=prediction_length,
        context_length=context_length,
        input_size=int(model_kwargs["input_size"]),
        n_layer=int(model_kwargs["n_layer"]),
        n_embd_per_head=int(model_kwargs["n_embd_per_head"]),
        n_head=int(model_kwargs["n_head"]),
        max_context_length=int(model_kwargs["max_context_length"]),
        rope_scaling=model_kwargs.get("rope_scaling"),
        scaling=model_kwargs["scaling"],
        num_parallel_samples=num_samples,
        time_feat=bool(model_kwargs["time_feat"]),
        dropout=float(model_kwargs["dropout"]),
        ckpt_path=None,
        device=device,
    )

    transformation = estimator.create_transformation()
    original_torch_load = torch.load

    def trusted_checkpoint_load(*args, **kwargs):
        kwargs["weights_only"] = False
        return original_torch_load(*args, **kwargs)

    try:
        torch.load = trusted_checkpoint_load

        module = estimator.create_lightning_module(use_kv_cache=False)

        state_dict = checkpoint.get("state_dict")

        if not isinstance(state_dict, dict):
            raise RuntimeError("checkpoint state_dict is missing")

        load_result = module.load_state_dict(
            state_dict,
            strict=True,
        )
    finally:
        torch.load = original_torch_load

    module = module.to(device).eval()
    parameter = next(module.parameters())

    predictor = estimator.create_predictor(
        transformation,
        module,
    )

    dataset = ListDataset(
        [
            {
                "start": pd.Period(
                    "2020-01-01",
                    freq="D",
                ),
                "target": series,
            }
            for series in history
        ],
        freq="D",
    )

    forecasts = list(predictor.predict(dataset))

    if len(forecasts) != 7:
        raise RuntimeError(f"expected 7 forecasts, got {len(forecasts)}")

    predictions = np.asarray(
        [float(np.median(np.asarray(forecast.samples)[:, 0])) for forecast in forecasts],
        dtype=float,
    )

    if execution_device == "cuda":
        torch.cuda.synchronize(0)

    if predictions.shape != (7,):
        raise RuntimeError(f"unexpected prediction shape: {predictions.shape}")

    if not np.isfinite(predictions).all():
        raise RuntimeError("non-finite Lag-Llama predictions")

    return {
        "status": "OK",
        "schema_version": 1,
        "provider_version": 1,
        "model_id": MODEL_ID,
        "repo_id": REPO_ID,
        "revision": revision,
        "snapshot_path": str(snapshot),
        "checkpoint_path": str(checkpoint_path),
        "model_class": type(module).__name__,
        "estimator_class": type(estimator).__name__,
        "checkpoint_state_entries": len(state_dict),
        "state_dict_missing_keys": list(load_result.missing_keys),
        "state_dict_unexpected_keys": list(load_result.unexpected_keys),
        "context_length": context_length,
        "prediction_length": prediction_length,
        "num_samples": num_samples,
        "input_shape": list(history.shape),
        "prediction_shape": list(predictions.shape),
        "predictions": predictions.tolist(),
        "finite": True,
        "properties": {
            "package": "lag-llama",
            "package_version": importlib.metadata.version("lag-llama"),
            "gluonts_version": importlib.metadata.version("gluonts"),
            "torch_version": torch.__version__,
            "checkpoint_sha256": _sha256(checkpoint_path),
            "checkpoint_size_bytes": checkpoint_path.stat().st_size,
            "checkpoint_hyper_parameters": hyper_parameters,
            "license": "apache-2.0",
            "snapshot_complete": True,
            "univariate_series_count": 7,
        },
        "gpu_evidence": {
            "requested_device": requested_device,
            "execution_device": execution_device,
            "cuda_available": cuda_available,
            "gpu_used": execution_device == "cuda",
            "cpu_fallback": (requested_device == "cuda" and execution_device != "cuda"),
            "model_device": str(parameter.device),
            "peak_vram_bytes": (
                int(torch.cuda.max_memory_allocated(0)) if execution_device == "cuda" else 0
            ),
            "gpu_pid": (os.getpid() if execution_device == "cuda" else None),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Lag-Llama provider")
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

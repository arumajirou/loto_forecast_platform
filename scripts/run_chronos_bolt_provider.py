#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import traceback
from pathlib import Path
from typing import Any

MODEL_ID = "chronos-bolt-tiny"
REPO_ID = "amazon/chronos-bolt-tiny"
REVISION = "a0e552de83495b5c28c14c71c374f3e33280b340"
WEIGHT_FILENAME = "model.safetensors"
CONFIG_FILENAME = "config.json"
QUANTILE_LEVELS = [
    0.1,
    0.2,
    0.3,
    0.4,
    0.5,
    0.6,
    0.7,
    0.8,
    0.9,
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _error(
    status: str,
    message: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "schema_version": 1,
        "provider_version": 1,
        "message": message,
    }


def run_provider(
    request: dict[str, Any],
) -> dict[str, Any]:
    model_id = str(request.get("model_id") or MODEL_ID)
    repo_id = str(request.get("repo_id") or REPO_ID)
    revision = str(request.get("revision") or REVISION)
    snapshot_value = request.get("snapshot_path")
    local_files_only = bool(request.get("local_files_only", True))
    requested_device = str(request.get("device") or "cuda")
    prediction_length = int(request.get("prediction_length", 1))

    if model_id != MODEL_ID:
        return _error(
            "PROVIDER_NOT_IMPLEMENTED",
            f"unsupported model_id: {model_id}",
        )

    if repo_id != REPO_ID:
        return _error(
            "PROVIDER_NOT_IMPLEMENTED",
            f"unsupported repo_id: {repo_id}",
        )

    if revision != REVISION:
        return _error(
            "PROVIDER_NOT_IMPLEMENTED",
            f"unsupported revision: {revision}",
        )

    if not local_files_only:
        return _error(
            "INVALID_REQUEST",
            "local_files_only must be true",
        )

    if requested_device != "cuda":
        return _error(
            "INVALID_REQUEST",
            "Chronos-Bolt runtime certification requires cuda",
        )

    if prediction_length != 1:
        return _error(
            "INVALID_REQUEST",
            "prediction_length must be 1",
        )

    if not snapshot_value:
        return _error(
            "MODEL_WEIGHTS_MISSING",
            "snapshot_path is required",
        )

    snapshot = Path(str(snapshot_value)).resolve()

    if snapshot.name != REVISION:
        return _error(
            "MODEL_WEIGHTS_MISSING",
            (f"snapshot directory does not match fixed revision: {snapshot}"),
        )

    weight_path = snapshot / WEIGHT_FILENAME
    config_path = snapshot / CONFIG_FILENAME

    if not weight_path.is_file():
        return _error(
            "MODEL_WEIGHTS_MISSING",
            f"fixed weight missing: {weight_path}",
        )

    if not config_path.is_file():
        return _error(
            "PARTIAL_SNAPSHOT",
            f"fixed config missing: {config_path}",
        )

    repo_cache_root = snapshot.parents[1]
    blobs_root = (repo_cache_root / "blobs").resolve()

    for path in (
        weight_path,
        config_path,
    ):
        real_path = path.resolve()

        try:
            real_path.relative_to(blobs_root)
        except ValueError:
            return _error(
                "INVALID_REQUEST",
                (f"snapshot file target is outside the fixed repository cache: {real_path}"),
            )

    history = request.get("history")

    if not isinstance(history, list):
        return _error(
            "INVALID_REQUEST",
            "history must be a list",
        )

    if len(history) < 2:
        return _error(
            "INVALID_REQUEST",
            "history must contain at least 2 rows",
        )

    try:
        matrix = [[float(row[f"n{position}"]) for row in history] for position in range(1, 8)]
    except Exception as exc:
        return _error(
            "INVALID_REQUEST",
            f"invalid history payload: {exc}",
        )

    import torch
    from chronos import BaseChronosPipeline

    if not torch.cuda.is_available():
        return _error(
            "CUDA_UNAVAILABLE",
            "CUDA is unavailable",
        )

    try:
        torch.cuda.set_device(0)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(0)

        pipeline = BaseChronosPipeline.from_pretrained(
            str(snapshot),
            device_map="cuda",
            torch_dtype=torch.float32,
            local_files_only=True,
        )

        model = getattr(
            pipeline,
            "model",
            getattr(
                pipeline,
                "inner_model",
                None,
            ),
        )

        if model is None:
            raise RuntimeError("loaded pipeline has no accessible model")

        parameter = next(model.parameters())

        if parameter.device.type != "cuda":
            raise RuntimeError(f"model did not load on CUDA: {parameter.device}")

        inputs = torch.tensor(
            matrix,
            dtype=torch.float32,
            device="cuda",
        )

        quantiles, mean = pipeline.predict_quantiles(
            inputs=inputs,
            prediction_length=1,
            quantile_levels=QUANTILE_LEVELS,
        )

        torch.cuda.synchronize(0)

        quantiles_cpu = quantiles.detach().cpu()
        mean_cpu = mean.detach().cpu()

        expected_quantile_shape = [
            7,
            1,
            len(QUANTILE_LEVELS),
        ]

        if list(quantiles_cpu.shape) != expected_quantile_shape:
            raise RuntimeError(f"unexpected quantile shape: {list(quantiles_cpu.shape)}")

        if list(mean_cpu.shape) != [7, 1]:
            raise RuntimeError(f"unexpected mean shape: {list(mean_cpu.shape)}")

        predictions = [float(value) for value in mean_cpu[:, 0].tolist()]

        if not all(math.isfinite(value) for value in predictions):
            raise RuntimeError("predictions contain non-finite values")

        peak_vram_bytes = int(torch.cuda.max_memory_allocated(0))

        if peak_vram_bytes <= 0:
            raise RuntimeError(f"non-positive peak VRAM: {peak_vram_bytes}")

        return {
            "status": "OK",
            "schema_version": 1,
            "provider_version": 1,
            "model_id": MODEL_ID,
            "repo_id": REPO_ID,
            "revision": REVISION,
            "snapshot_path": str(snapshot),
            "predictions": predictions,
            "prediction_shape": [7],
            "quantiles": (quantiles_cpu[:, 0, :].tolist()),
            "quantile_levels": QUANTILE_LEVELS,
            "quantile_shape": (list(quantiles_cpu.shape)),
            "mean_shape": list(mean_cpu.shape),
            "finite": True,
            "properties": {
                "library": "chronos",
                "package": ("chronos-forecasting"),
                "pipeline_class": type(pipeline).__name__,
                "model_class": type(model).__name__,
                "backend": "torch",
                "context_length": len(history),
                "prediction_length": 1,
                "weight_path": str(weight_path),
                "weight_sha256": _sha256(weight_path),
                "config_path": str(config_path),
                "config_sha256": _sha256(config_path),
                "parameter_dtype": str(parameter.dtype),
                "license": "Apache-2.0",
                "license_commercial_use": True,
            },
            "gpu_evidence": {
                "requested_device": "cuda",
                "execution_device": str(parameter.device),
                "cuda_available": True,
                "gpu_requested": True,
                "gpu_used": True,
                "gpu_certification": ("OBSERVED"),
                "resource_certification": ("GPU_PASS"),
                "cpu_fallback": False,
                "fallback_reason": None,
                "peak_vram_bytes": (peak_vram_bytes),
                "gpu_pid": __import__("os").getpid(),
            },
            "artifact_reference": {
                "repo_id": REPO_ID,
                "revision": REVISION,
                "snapshot_path": str(snapshot),
            },
        }

    except Exception as exc:
        return {
            "status": "ERROR",
            "schema_version": 1,
            "provider_version": 1,
            "model_id": MODEL_ID,
            "repo_id": REPO_ID,
            "revision": REVISION,
            "message": str(exc),
            "error_type": type(exc).__name__,
            "traceback": traceback.format_exc(),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--request",
        required=True,
    )
    parser.add_argument(
        "--response",
        required=True,
    )
    args = parser.parse_args()

    request_path = Path(args.request)
    response_path = Path(args.response)

    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        response = run_provider(request)
    except Exception as exc:
        response = {
            "status": "ERROR",
            "schema_version": 1,
            "provider_version": 1,
            "message": str(exc),
            "error_type": type(exc).__name__,
            "traceback": traceback.format_exc(),
        }

    response_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    response_path.write_text(
        json.dumps(
            response,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())

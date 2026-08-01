#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import traceback
from pathlib import Path
from typing import Any

MODEL_ID = "chronos-2"
REPO_ID = "amazon/chronos-2"
REVISION = "29ec3766d36d6f73f0696f85560a422f50e8498c"

WEIGHT_FILENAME = "model.safetensors"
CONFIG_FILENAME = "config.json"

WEIGHT_SHA256 = "ddcda3c7508bf2528087723e98a20707cc04b7f370ae275a9fd88078ddba4f42"
CONFIG_SHA256 = "ef1143bfdc9c0376d9a056eefca46cb4b1ec3d0ffacd541ff56feb40fb708031"

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

FIXED_SEED = 42
FIXED_PREDICTION_LENGTH = 1
FIXED_BATCH_SIZE = 7
FIXED_CONTEXT_LENGTH = 512
FIXED_CROSS_LEARNING = False


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
        "schema_version": 1,
        "provider_version": 1,
        "status": status,
        "model_id": MODEL_ID,
        "repo_id": REPO_ID,
        "revision": REVISION,
        "message": message,
    }


def _validate_snapshot(
    snapshot: Path,
) -> dict[str, Any]:
    if not snapshot.is_dir():
        raise RuntimeError(f"fixed snapshot missing: {snapshot}")

    if snapshot.name != REVISION:
        raise RuntimeError(
            f"snapshot revision mismatch: expected={REVISION}, actual={snapshot.name}"
        )

    weight_path = snapshot / WEIGHT_FILENAME
    config_path = snapshot / CONFIG_FILENAME

    if not weight_path.is_file():
        raise RuntimeError(f"fixed weight missing: {weight_path}")

    if not config_path.is_file():
        raise RuntimeError(f"fixed config missing: {config_path}")

    repo_cache_root = snapshot.parents[1]
    blobs_root = (repo_cache_root / "blobs").resolve()

    for path in (
        weight_path,
        config_path,
    ):
        real_path = path.resolve()

        try:
            real_path.relative_to(blobs_root)
        except ValueError as exc:
            raise RuntimeError(
                f"snapshot file target is outside the fixed repository cache: {real_path}"
            ) from exc

    actual_weight_sha256 = _sha256(weight_path)
    actual_config_sha256 = _sha256(config_path)

    if actual_weight_sha256 != WEIGHT_SHA256:
        raise RuntimeError(f"weight SHA-256 mismatch: {actual_weight_sha256}")

    if actual_config_sha256 != CONFIG_SHA256:
        raise RuntimeError(f"config SHA-256 mismatch: {actual_config_sha256}")

    return {
        "snapshot_path": str(snapshot),
        "weight_path": str(weight_path),
        "weight_sha256": actual_weight_sha256,
        "config_path": str(config_path),
        "config_sha256": actual_config_sha256,
    }


def run_provider(
    request: dict[str, Any],
) -> dict[str, Any]:
    model_id = str(request.get("model_id") or MODEL_ID)
    repo_id = str(request.get("repo_id") or REPO_ID)
    revision = str(request.get("revision") or REVISION)
    requested_device = str(request.get("device") or "cuda")
    local_files_only = request.get(
        "local_files_only",
        True,
    )
    snapshot_value = request.get("snapshot_path")
    prediction_length = int(
        request.get(
            "prediction_length",
            FIXED_PREDICTION_LENGTH,
        )
    )
    batch_size = int(
        request.get(
            "batch_size",
            FIXED_BATCH_SIZE,
        )
    )
    context_length = int(
        request.get(
            "context_length",
            FIXED_CONTEXT_LENGTH,
        )
    )
    cross_learning = request.get(
        "cross_learning",
        FIXED_CROSS_LEARNING,
    )
    seed = int(request.get("seed", FIXED_SEED))

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

    if local_files_only is not True:
        return _error(
            "INVALID_REQUEST",
            "local_files_only must be true",
        )

    if requested_device != "cuda":
        return _error(
            "INVALID_REQUEST",
            "Chronos 2 runtime certification requires cuda",
        )

    if prediction_length != FIXED_PREDICTION_LENGTH:
        return _error(
            "INVALID_REQUEST",
            "prediction_length must be 1",
        )

    if batch_size != FIXED_BATCH_SIZE:
        return _error(
            "INVALID_REQUEST",
            "batch_size must be 7",
        )

    if context_length != FIXED_CONTEXT_LENGTH:
        return _error(
            "INVALID_REQUEST",
            "context_length must be 512",
        )

    if cross_learning is not False:
        return _error(
            "INVALID_REQUEST",
            "cross_learning must be false",
        )

    if seed != FIXED_SEED:
        return _error(
            "INVALID_REQUEST",
            "seed must be 42",
        )

    if not snapshot_value:
        return _error(
            "MODEL_WEIGHTS_MISSING",
            "snapshot_path is required",
        )

    snapshot = Path(str(snapshot_value)).resolve()

    try:
        artifact = _validate_snapshot(snapshot)
    except Exception as exc:
        return _error(
            "MODEL_WEIGHTS_MISSING",
            str(exc),
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

    if len(history) > FIXED_CONTEXT_LENGTH:
        history = history[-FIXED_CONTEXT_LENGTH:]

    try:
        matrix = [[float(row[f"n{position}"]) for row in history] for position in range(1, 8)]
    except Exception as exc:
        return _error(
            "INVALID_REQUEST",
            f"invalid history payload: {exc}",
        )

    try:
        import torch
        from chronos import BaseChronosPipeline

        if not torch.cuda.is_available():
            return _error(
                "CUDA_UNAVAILABLE",
                "CUDA is unavailable",
            )

        torch.manual_seed(FIXED_SEED)
        torch.cuda.manual_seed_all(FIXED_SEED)

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
            raise RuntimeError("loaded pipeline exposes no model")

        parameter = next(model.parameters())

        if parameter.device.type != "cuda":
            raise RuntimeError(f"model did not load on CUDA: {parameter.device}")

        inputs = [
            torch.tensor(
                series,
                dtype=torch.float32,
                device="cpu",
            )
            for series in matrix
        ]

        quantiles, means = pipeline.predict_quantiles(
            inputs=inputs,
            prediction_length=(FIXED_PREDICTION_LENGTH),
            quantile_levels=QUANTILE_LEVELS,
            batch_size=FIXED_BATCH_SIZE,
            context_length=FIXED_CONTEXT_LENGTH,
            cross_learning=FIXED_CROSS_LEARNING,
        )

        torch.cuda.synchronize(0)

        if not isinstance(quantiles, list):
            raise RuntimeError("quantiles output is not a list")

        if not isinstance(means, list):
            raise RuntimeError("means output is not a list")

        if len(quantiles) != 7:
            raise RuntimeError(f"unexpected quantile list length: {len(quantiles)}")

        if len(means) != 7:
            raise RuntimeError(f"unexpected mean list length: {len(means)}")

        expected_quantile_shape = [1, 1, 9]
        expected_mean_shape = [1, 1]

        quantile_values = []
        predictions = []

        for index, item in enumerate(quantiles):
            tensor = item.detach().cpu()

            if list(tensor.shape) != (expected_quantile_shape):
                raise RuntimeError(
                    f"unexpected quantile shape at index {index}: {list(tensor.shape)}"
                )

            quantile_values.append(tensor.reshape(9).tolist())

        for index, item in enumerate(means):
            tensor = item.detach().cpu()

            if list(tensor.shape) != (expected_mean_shape):
                raise RuntimeError(f"unexpected mean shape at index {index}: {list(tensor.shape)}")

            predictions.append(float(tensor.reshape(-1)[0]))

        if not all(math.isfinite(value) for value in predictions):
            raise RuntimeError("predictions contain non-finite values")

        peak_vram_bytes = int(torch.cuda.max_memory_allocated(0))

        if peak_vram_bytes <= 0:
            raise RuntimeError(f"non-positive peak VRAM: {peak_vram_bytes}")

        return {
            "schema_version": 1,
            "provider_version": 1,
            "status": "OK",
            "model_id": MODEL_ID,
            "repo_id": REPO_ID,
            "revision": REVISION,
            "snapshot_path": str(snapshot),
            "predictions": predictions,
            "prediction_shape": [7],
            "quantiles": quantile_values,
            "quantile_levels": QUANTILE_LEVELS,
            "quantile_list_length": 7,
            "mean_list_length": 7,
            "quantile_shapes": [expected_quantile_shape for _ in range(7)],
            "mean_shapes": [expected_mean_shape for _ in range(7)],
            "finite": True,
            "properties": {
                "library": "chronos",
                "package": "chronos-forecasting",
                "pipeline_class": type(pipeline).__name__,
                "model_class": type(model).__name__,
                "backend": "torch",
                "context_length": len(history),
                "maximum_context_length": (FIXED_CONTEXT_LENGTH),
                "prediction_length": (FIXED_PREDICTION_LENGTH),
                "batch_size": (FIXED_BATCH_SIZE),
                "cross_learning": (FIXED_CROSS_LEARNING),
                "seed": FIXED_SEED,
                "input_devices": [str(item.device) for item in inputs],
                "model_device": str(parameter.device),
                "parameter_dtype": str(parameter.dtype),
                "license": "Apache-2.0",
                "license_commercial_use": True,
                **artifact,
            },
            "gpu_evidence": {
                "requested_device": "cuda",
                "execution_device": str(parameter.device),
                "model_device": str(parameter.device),
                "input_devices": [str(item.device) for item in inputs],
                "cuda_available": True,
                "gpu_requested": True,
                "gpu_used": True,
                "gpu_certification": "OBSERVED",
                "resource_certification": "GPU_PASS",
                "cpu_fallback": False,
                "cpu_preprocessing": True,
                "cpu_preprocessing_reason": (
                    "Chronos 2 input preprocessing operates on CPU before CUDA inference"
                ),
                "fallback_reason": None,
                "peak_vram_bytes": peak_vram_bytes,
                "gpu_pid": os.getpid(),
            },
            "artifact_reference": {
                "repo_id": REPO_ID,
                "revision": REVISION,
                "snapshot_path": str(snapshot),
            },
        }

    except Exception as exc:
        return {
            "schema_version": 1,
            "provider_version": 1,
            "status": "ERROR",
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
            "schema_version": 1,
            "provider_version": 1,
            "status": "ERROR",
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

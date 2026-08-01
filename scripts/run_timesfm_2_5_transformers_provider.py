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

MODEL_ID = "timesfm-2.5-transformers"
REPO_ID = "google/timesfm-2.5-200m-transformers"
REVISION = "5a9806b9b291fad9233b5249d88263f1846304d3"

SNAPSHOT = Path(
    f"/mnt/e/env/huggingface/hub/models--google--timesfm-2.5-200m-transformers/snapshots/{REVISION}"
)

SERIES_COUNT = 7
CONTEXT_LENGTH = 512
CERTIFICATION_PREDICTION_LENGTH = 1
FIXED_SEED = 42


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def error_result(
    status: str,
    message: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": status,
        "model_id": MODEL_ID,
        "repo_id": REPO_ID,
        "revision": REVISION,
        "message": message,
    }


def validate_snapshot(snapshot: Path) -> dict[str, Any]:
    if not snapshot.is_dir():
        raise RuntimeError(f"fixed snapshot missing: {snapshot}")

    if snapshot.name != REVISION:
        raise RuntimeError(
            f"snapshot revision mismatch: expected={REVISION}, actual={snapshot.name}"
        )

    config = snapshot / "config.json"
    weight = snapshot / "model.safetensors"

    if not config.is_file():
        raise RuntimeError(f"config.json missing: {config}")

    if not weight.is_file():
        raise RuntimeError(f"model.safetensors missing: {weight}")

    return {
        "snapshot_path": str(snapshot),
        "config_path": str(config),
        "config_sha256": sha256(config),
        "weight_path": str(weight),
        "weight_sha256": sha256(weight),
        "weight_size_bytes": weight.stat().st_size,
    }


def run(request: dict[str, Any]) -> dict[str, Any]:
    try:
        import torch
        from transformers import (
            TimesFm2_5ModelForPrediction,
        )

        if request.get("model_id") != MODEL_ID:
            return error_result(
                "INVALID_REQUEST",
                "model_id mismatch",
            )

        if request.get("repo_id") != REPO_ID:
            return error_result(
                "INVALID_REQUEST",
                "repo_id mismatch",
            )

        if request.get("revision") != REVISION:
            return error_result(
                "INVALID_REQUEST",
                "revision mismatch",
            )

        if request.get("local_files_only") is not True:
            return error_result(
                "INVALID_REQUEST",
                "local_files_only must be true",
            )

        if request.get("device") != "cuda":
            return error_result(
                "INVALID_REQUEST",
                "device must be cuda",
            )

        history = request.get("history")

        if not isinstance(history, list):
            return error_result(
                "INVALID_REQUEST",
                "history must be a list",
            )

        if len(history) < 2:
            return error_result(
                "INVALID_REQUEST",
                "history must contain at least two rows",
            )

        artifact = validate_snapshot(SNAPSHOT)

        matrix = [
            [float(row[f"n{position}"]) for row in history[-CONTEXT_LENGTH:]]
            for position in range(1, 8)
        ]

        for series in matrix:
            if len(series) < CONTEXT_LENGTH:
                series[:0] = [series[0]] * (CONTEXT_LENGTH - len(series))

        torch.manual_seed(FIXED_SEED)
        torch.cuda.manual_seed_all(FIXED_SEED)
        torch.cuda.set_device(0)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(0)

        model = TimesFm2_5ModelForPrediction.from_pretrained(
            str(SNAPSHOT),
            local_files_only=True,
            torch_dtype=torch.float32,
        )

        model = model.to("cuda").eval()
        parameter = next(model.parameters())

        if parameter.device.type != "cuda":
            raise RuntimeError(f"model not on CUDA: {parameter.device}")

        past_values = [
            torch.tensor(
                series,
                dtype=torch.float32,
                device="cuda",
            )
            for series in matrix
        ]

        with torch.inference_mode():
            outputs = model(
                past_values=past_values,
                return_dict=True,
            )

        torch.cuda.synchronize(0)

        mean_predictions = outputs.mean_predictions
        full_predictions = outputs.full_predictions

        if list(mean_predictions.shape) != [7, 128]:
            raise RuntimeError(f"unexpected mean shape: {list(mean_predictions.shape)}")

        if list(full_predictions.shape) != [7, 128, 10]:
            raise RuntimeError(f"unexpected full shape: {list(full_predictions.shape)}")

        if not torch.isfinite(mean_predictions).all():
            raise RuntimeError("mean predictions are non-finite")

        if not torch.isfinite(full_predictions).all():
            raise RuntimeError("full predictions are non-finite")

        point = mean_predictions[
            :,
            :CERTIFICATION_PREDICTION_LENGTH,
        ]

        full_step = full_predictions[
            :,
            :CERTIFICATION_PREDICTION_LENGTH,
            :,
        ]

        predictions = [float(value) for value in point[:, 0].detach().cpu().tolist()]

        if not all(math.isfinite(value) for value in predictions):
            raise RuntimeError("point predictions are non-finite")

        peak_vram_bytes = int(torch.cuda.max_memory_allocated(0))

        if peak_vram_bytes <= 0:
            raise RuntimeError("peak VRAM is not positive")

        return {
            "schema_version": 1,
            "status": "OK",
            "model_id": MODEL_ID,
            "repo_id": REPO_ID,
            "revision": REVISION,
            "runtime_pid": os.getpid(),
            "prediction_values": predictions,
            "prediction_shape": list(point.shape),
            "full_prediction_shape": list(full_step.shape),
            "native_mean_shape": list(mean_predictions.shape),
            "native_full_shape": list(full_predictions.shape),
            "output_finite": True,
            "properties": {
                "model_class": type(model).__name__,
                "output_class": type(outputs).__name__,
                "context_length": CONTEXT_LENGTH,
                "native_prediction_length": 128,
                "certification_prediction_length": 1,
                "series_count": SERIES_COUNT,
                "parameter_dtype": str(parameter.dtype),
                "license": "Apache-2.0",
                "commercial_use": True,
                "runtime_certification_scope": ("FULL_INFERENCE"),
                **artifact,
            },
            "gpu_evidence": {
                "requested_device": "cuda",
                "model_device": str(parameter.device),
                "input_devices": sorted({str(value.device) for value in past_values}),
                "mean_output_device": str(mean_predictions.device),
                "full_output_device": str(full_predictions.device),
                "gpu_used": True,
                "cpu_fallback": False,
                "peak_vram_bytes": (peak_vram_bytes),
                "gpu_pid": os.getpid(),
            },
        }

    except Exception as exc:
        return {
            "schema_version": 1,
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

    request = json.loads(Path(args.request).read_text(encoding="utf-8"))

    response = run(request)

    Path(args.response).write_text(
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

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

MODEL_ID = "moment-1-large"
REPO_ID = "AutonLab/MOMENT-1-large"
REVISION = "ca58581bc7bea2ebed4e80dc0a3e4b8b609c6ecc"

SNAPSHOT = Path(f"/mnt/e/env/huggingface/hub/models--AutonLab--MOMENT-1-large/snapshots/{REVISION}")

CONTEXT_LENGTH = 512
PREDICTION_LENGTH = 1
SERIES_COUNT = 7
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

    weight_candidates = sorted(list(snapshot.glob("*.safetensors")) + list(snapshot.glob("*.bin")))

    if not config.is_file():
        raise RuntimeError(f"config.json missing: {config}")

    if not weight_candidates:
        raise RuntimeError(f"model weights missing: {snapshot}")

    weights = [
        {
            "name": path.name,
            "path": str(path),
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in weight_candidates
    ]

    return {
        "snapshot_path": str(snapshot),
        "config_path": str(config),
        "config_sha256": sha256(config),
        "weights": weights,
    }


def run(request: dict[str, Any]) -> dict[str, Any]:
    try:
        import torch
        from momentfm import MOMENTPipeline

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

        # Left-pad to the fixed 512-point context.
        for series in matrix:
            if len(series) < CONTEXT_LENGTH:
                pad_value = series[0]
                series[:0] = [pad_value] * (CONTEXT_LENGTH - len(series))

        torch.manual_seed(FIXED_SEED)
        torch.cuda.manual_seed_all(FIXED_SEED)

        torch.cuda.set_device(0)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(0)

        model = MOMENTPipeline.from_pretrained(
            str(SNAPSHOT),
            model_kwargs={
                "task_name": "forecasting",
                "forecast_horizon": PREDICTION_LENGTH,
            },
            local_files_only=True,
        )

        model.init()
        model = model.to("cuda").eval()

        parameter = next(model.parameters())

        if parameter.device.type != "cuda":
            raise RuntimeError(f"model is not on CUDA: {parameter.device}")

        inputs = torch.tensor(
            matrix,
            dtype=torch.float32,
            device="cuda",
        ).unsqueeze(1)

        input_mask = torch.ones(
            SERIES_COUNT,
            CONTEXT_LENGTH,
            dtype=torch.long,
            device="cuda",
        )

        with torch.inference_mode():
            outputs = model(
                x_enc=inputs,
                input_mask=input_mask,
            )

        torch.cuda.synchronize(0)

        forecast = outputs.forecast

        if forecast is None:
            raise RuntimeError("MOMENT returned no forecast tensor")

        expected_shape = [
            SERIES_COUNT,
            1,
            PREDICTION_LENGTH,
        ]

        if list(forecast.shape) != expected_shape:
            raise RuntimeError(f"unexpected forecast shape: {list(forecast.shape)}")

        if not torch.isfinite(forecast).all():
            raise RuntimeError("forecast contains non-finite values")

        predictions = [float(value) for value in forecast[:, 0, 0].detach().cpu().tolist()]

        if not all(math.isfinite(value) for value in predictions):
            raise RuntimeError("prediction values are not finite")

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
            "prediction_shape": list(forecast.shape),
            "output_finite": True,
            "properties": {
                "pipeline_class": (type(model).__name__),
                "output_class": (type(outputs).__name__),
                "context_length": CONTEXT_LENGTH,
                "prediction_length": (PREDICTION_LENGTH),
                "series_count": SERIES_COUNT,
                "task_name": "forecasting",
                "forecast_head_pretrained": False,
                "forecast_head_status": ("FINE_TUNING_REQUIRED"),
                "runtime_certification_scope": ("EXECUTION_ONLY"),
                "license": "MIT",
                "commercial_use": True,
                **artifact,
            },
            "gpu_evidence": {
                "requested_device": "cuda",
                "model_device": str(parameter.device),
                "input_device": str(inputs.device),
                "output_device": str(forecast.device),
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

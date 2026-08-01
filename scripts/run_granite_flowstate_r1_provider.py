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

MODEL_ID = "granite-flowstate-r1"
REPO_ID = "ibm-granite/granite-timeseries-flowstate-r1"
REVISION = "05effc6cb39ee16dce9dd0064ed1a76e4b8ff464"

SNAPSHOT = Path(
    "/mnt/e/env/huggingface/hub/"
    "models--ibm-granite--granite-timeseries-flowstate-r1/"
    "snapshots/"
    f"{REVISION}"
)

SERIES_COUNT = 7
CONTEXT_LENGTH = 2048
PREDICTION_LENGTH = 24
CHANNEL_COUNT = 1
QUANTILE_COUNT = 9
SCALE_FACTOR = 1.0
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


def validate_snapshot() -> dict[str, Any]:
    if not SNAPSHOT.is_dir():
        raise RuntimeError(f"fixed snapshot missing: {SNAPSHOT}")

    if SNAPSHOT.name != REVISION:
        raise RuntimeError(
            f"snapshot revision mismatch: expected={REVISION}, actual={SNAPSHOT.name}"
        )

    required = {
        "config.json": SNAPSHOT / "config.json",
        "model.safetensors": SNAPSHOT / "model.safetensors",
        "model.sig": SNAPSHOT / "model.sig",
        "README.md": SNAPSHOT / "README.md",
    }

    missing = [name for name, path in required.items() if not path.is_file()]

    if missing:
        raise RuntimeError("required snapshot files missing: " + ", ".join(missing))

    return {
        "snapshot_path": str(SNAPSHOT),
        "config_sha256": sha256(required["config.json"]),
        "weight_sha256": sha256(required["model.safetensors"]),
        "weight_size_bytes": required["model.safetensors"].stat().st_size,
        "signature_sha256": sha256(required["model.sig"]),
        "readme_sha256": sha256(required["README.md"]),
        "files": {
            name: {
                "path": str(path),
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for name, path in required.items()
        },
    }


def run(request: dict[str, Any]) -> dict[str, Any]:
    try:
        import torch
        from tsfm_public import FlowStateForPrediction

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

        artifact = validate_snapshot()

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

        predictor = (
            FlowStateForPrediction.from_pretrained(
                str(SNAPSHOT),
                local_files_only=True,
            )
            .to("cuda")
            .eval()
        )

        parameter = next(predictor.parameters())

        if parameter.device.type != "cuda":
            raise RuntimeError(f"model not on CUDA: {parameter.device}")

        # FlowState input:
        # context, batch, channels
        time_series = (
            torch.tensor(
                matrix,
                dtype=torch.float32,
                device="cuda",
            )
            .transpose(0, 1)
            .unsqueeze(-1)
            .contiguous()
        )

        if list(time_series.shape) != [2048, 7, 1]:
            raise RuntimeError(f"unexpected input shape: {list(time_series.shape)}")

        with torch.inference_mode():
            forecast = predictor(
                time_series,
                scale_factor=SCALE_FACTOR,
                prediction_length=PREDICTION_LENGTH,
                batch_first=False,
                return_dict=True,
            )

        torch.cuda.synchronize(0)

        mean_outputs = forecast.prediction_outputs
        quantile_outputs = forecast.quantile_outputs

        if list(mean_outputs.shape) != [7, 24, 1]:
            raise RuntimeError(f"unexpected mean shape: {list(mean_outputs.shape)}")

        if list(quantile_outputs.shape) != [7, 9, 24, 1]:
            raise RuntimeError(f"unexpected quantile shape: {list(quantile_outputs.shape)}")

        if not torch.isfinite(mean_outputs).all():
            raise RuntimeError("mean outputs are non-finite")

        if not torch.isfinite(quantile_outputs).all():
            raise RuntimeError("quantile outputs are non-finite")

        point = mean_outputs[:, :1, :]

        prediction_values = [float(value) for value in point[:, 0, 0].detach().cpu().tolist()]

        if not all(math.isfinite(value) for value in prediction_values):
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
            "prediction_values": prediction_values,
            "certification_prediction_shape": list(point.shape),
            "mean_prediction_shape": list(mean_outputs.shape),
            "quantile_prediction_shape": list(quantile_outputs.shape),
            "output_finite": True,
            "properties": {
                "model_class": type(predictor).__name__,
                "output_class": type(forecast).__name__,
                "parameter_count": sum(value.numel() for value in predictor.parameters()),
                "context_length": CONTEXT_LENGTH,
                "prediction_length": PREDICTION_LENGTH,
                "series_count": SERIES_COUNT,
                "channel_count": CHANNEL_COUNT,
                "quantile_count": QUANTILE_COUNT,
                "scale_factor": SCALE_FACTOR,
                "parameter_dtype": str(parameter.dtype),
                "license": "Apache-2.0",
                "commercial_use": True,
                "runtime_certification_scope": ("FULL_INFERENCE"),
                "forecast_head_executed": True,
                "forecast_accuracy_certified": False,
                **artifact,
            },
            "gpu_evidence": {
                "requested_device": "cuda",
                "model_device": str(parameter.device),
                "input_device": str(time_series.device),
                "mean_output_device": str(mean_outputs.device),
                "quantile_output_device": str(quantile_outputs.device),
                "gpu_used": True,
                "cpu_fallback": False,
                "peak_vram_bytes": peak_vram_bytes,
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

#!/usr/bin/env python3
"""Run the fixed-revision Granite TTM GPU runtime probe."""

from __future__ import annotations

import argparse
import json
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from tsfm_public import TinyTimeMixerForPrediction

MODEL_ID = "granite-ttm-r2"
REPO_ID = "ibm-granite/granite-timeseries-ttm-r2"
REVISION = "d6a79570cac0f33d526601cd3a0fc7c80a8f9a2f"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    device_index = 0
    device = torch.device(f"cuda:{device_index}")
    started = time.perf_counter()

    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": "BLOCKED",
        "model_id": MODEL_ID,
        "repo_id": REPO_ID,
        "revision": REVISION,
        "started_at": datetime.now(UTC).isoformat(),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "compiled_arch_list": (torch.cuda.get_arch_list() if torch.cuda.is_available() else []),
        "runtime_vram_certified": False,
    }

    try:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable")

        if "sm_120" not in torch.cuda.get_arch_list():
            raise RuntimeError("installed PyTorch does not include sm_120")

        torch.cuda.set_device(device_index)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(device_index)

        baseline_allocated = torch.cuda.memory_allocated(device_index)
        baseline_reserved = torch.cuda.memory_reserved(device_index)

        load_started = time.perf_counter()

        model = TinyTimeMixerForPrediction.from_pretrained(
            REPO_ID,
            revision=REVISION,
            trust_remote_code=False,
        )

        load_seconds = time.perf_counter() - load_started

        model = model.to(device)
        model.eval()

        first_parameter = next(model.parameters())

        if first_parameter.device.type != "cuda":
            raise RuntimeError(f"model parameters not on CUDA: {first_parameter.device}")

        context_length = int(model.config.context_length)

        # Preserve the current provider contract:
        # seven independent one-channel series.
        past_values = torch.linspace(
            0.0,
            1.0,
            steps=7 * context_length,
            dtype=first_parameter.dtype,
            device=device,
        ).reshape(7, context_length, 1)

        torch.cuda.synchronize(device_index)
        inference_started = time.perf_counter()

        with torch.inference_mode():
            output = model(past_values=past_values)

        torch.cuda.synchronize(device_index)

        inference_seconds = time.perf_counter() - inference_started

        prediction = getattr(
            output,
            "prediction_outputs",
            None,
        )

        if not isinstance(prediction, torch.Tensor):
            raise RuntimeError("prediction_outputs tensor not returned")

        if prediction.device.type != "cuda":
            raise RuntimeError(f"prediction not on CUDA: {prediction.device}")

        finite = bool(torch.isfinite(prediction).all().item())

        if not finite:
            raise RuntimeError("prediction contains NaN or Inf")

        parameter_count = sum(parameter.numel() for parameter in model.parameters())

        payload.update(
            {
                "status": "PASS",
                "completed_at": datetime.now(UTC).isoformat(),
                "load_seconds": load_seconds,
                "inference_seconds": inference_seconds,
                "total_seconds": time.perf_counter() - started,
                "device": str(device),
                "device_index": device_index,
                "gpu_name": torch.cuda.get_device_name(device_index),
                "compute_capability": list(torch.cuda.get_device_capability(device_index)),
                "parameter_device": str(first_parameter.device),
                "parameter_dtype": str(first_parameter.dtype),
                "parameter_count": parameter_count,
                "context_length": context_length,
                "prediction_length": int(model.config.prediction_length),
                "num_input_channels": int(model.config.num_input_channels),
                "input_shape": list(past_values.shape),
                "prediction_shape": list(prediction.shape),
                "prediction_finite": finite,
                "baseline_allocated_bytes": (baseline_allocated),
                "baseline_reserved_bytes": (baseline_reserved),
                "peak_allocated_bytes": (torch.cuda.max_memory_allocated(device_index)),
                "peak_reserved_bytes": (torch.cuda.max_memory_reserved(device_index)),
                "runtime_vram_certified": True,
            }
        )

    except Exception as exc:
        payload.update(
            {
                "status": "BLOCKED",
                "completed_at": datetime.now(UTC).isoformat(),
                "total_seconds": time.perf_counter() - started,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )

    args.output.write_text(
        json.dumps(payload, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

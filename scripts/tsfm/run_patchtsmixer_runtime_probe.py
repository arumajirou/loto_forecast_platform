#!/usr/bin/env python3
"""Run one fixed-revision PatchTSMixer GPU inference probe."""

from __future__ import annotations

import argparse
import json
import platform
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from transformers import (
    PatchTSMixerConfig,
    PatchTSMixerForPrediction,
)

MODEL_ID = "granite-patchtsmixer"
REPO_ID = "ibm-granite/granite-timeseries-patchtsmixer"
REVISION = "90dc5a88d45f032b7dceefb5d814ca2af54f2ff9"


def tensor_shape(value: Any) -> list[int] | None:
    if isinstance(value, torch.Tensor):
        return list(value.shape)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(UTC).isoformat()
    start = time.perf_counter()

    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": "BLOCKED",
        "model_id": MODEL_ID,
        "repo_id": REPO_ID,
        "revision": REVISION,
        "started_at": started_at,
        "python": platform.python_version(),
        "torch": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "runtime_vram_certified": False,
    }

    try:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable")

        device_index = 0
        device = torch.device(f"cuda:{device_index}")

        torch.cuda.set_device(device_index)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(device_index)

        baseline_allocated = torch.cuda.memory_allocated(device_index)
        baseline_reserved = torch.cuda.memory_reserved(device_index)

        config = PatchTSMixerConfig.from_pretrained(
            REPO_ID,
            revision=REVISION,
            trust_remote_code=False,
        )

        context_length = int(config.context_length)
        channels = int(config.num_input_channels)

        load_start = time.perf_counter()

        model = PatchTSMixerForPrediction.from_pretrained(
            REPO_ID,
            revision=REVISION,
            trust_remote_code=False,
            local_files_only=False,
        )

        load_seconds = time.perf_counter() - load_start

        model = model.to(device)
        model.eval()

        first_parameter = next(model.parameters())
        parameter_device = str(first_parameter.device)
        parameter_dtype = str(first_parameter.dtype)
        parameter_count = sum(parameter.numel() for parameter in model.parameters())

        if first_parameter.device.type != "cuda":
            raise RuntimeError(f"model parameter is not on CUDA: {parameter_device}")

        past_values = torch.linspace(
            0.0,
            1.0,
            steps=context_length * channels,
            dtype=first_parameter.dtype,
            device=device,
        ).reshape(1, context_length, channels)

        observed_mask = torch.ones_like(
            past_values,
            dtype=torch.bool,
            device=device,
        )

        torch.cuda.synchronize(device_index)
        inference_start = time.perf_counter()

        with torch.inference_mode():
            outputs = model(
                past_values=past_values,
                observed_mask=observed_mask,
            )

        torch.cuda.synchronize(device_index)
        inference_seconds = time.perf_counter() - inference_start

        prediction_outputs = getattr(
            outputs,
            "prediction_outputs",
            None,
        )

        if not isinstance(prediction_outputs, torch.Tensor):
            raise RuntimeError("prediction_outputs tensor was not returned")

        if prediction_outputs.device.type != "cuda":
            raise RuntimeError("prediction output was not produced on CUDA")

        finite = bool(torch.isfinite(prediction_outputs).all().item())

        if not finite:
            raise RuntimeError("prediction output contains NaN or Inf")

        peak_allocated = torch.cuda.max_memory_allocated(device_index)
        peak_reserved = torch.cuda.max_memory_reserved(device_index)

        payload.update(
            {
                "status": "PASS",
                "completed_at": datetime.now(UTC).isoformat(),
                "load_seconds": load_seconds,
                "inference_seconds": inference_seconds,
                "total_seconds": time.perf_counter() - start,
                "device": str(device),
                "gpu_name": torch.cuda.get_device_name(device),
                "compute_capability": list(torch.cuda.get_device_capability(device)),
                "parameter_device": parameter_device,
                "parameter_dtype": parameter_dtype,
                "parameter_count": parameter_count,
                "context_length": context_length,
                "prediction_length": int(config.prediction_length),
                "num_input_channels": channels,
                "input_shape": tensor_shape(past_values),
                "prediction_shape": tensor_shape(prediction_outputs),
                "prediction_finite": finite,
                "baseline_allocated_bytes": baseline_allocated,
                "baseline_reserved_bytes": baseline_reserved,
                "peak_allocated_bytes": peak_allocated,
                "peak_reserved_bytes": peak_reserved,
                "runtime_vram_certified": True,
            }
        )

    except Exception as exc:
        payload.update(
            {
                "status": "BLOCKED",
                "completed_at": datetime.now(UTC).isoformat(),
                "total_seconds": time.perf_counter() - start,
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

from __future__ import annotations

import gc
import json
import math
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from neuralforecast import NeuralForecast
from neuralforecast.losses.pytorch import MAE
from neuralforecast.models import (
    DLinear,
    MLP,
    NBEATS,
    NHITS,
    NLinear,
    PatchTST,
)


OUTPUT = Path("artifacts/runtime_certification/neuralforecast_fit_predict_gpu_phase1.json")

PREDICTION_DIR = Path(
    "artifacts/runtime_certification/neuralforecast_fit_predict_gpu_phase1_predictions"
)

HORIZON = 1
INPUT_SIZE = 16
MAX_STEPS = 2
SEED = 42

torch.set_float32_matmul_precision("high")


def make_data() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    rows: list[dict[str, Any]] = []

    dates = pd.date_range(
        "2025-01-01",
        periods=96,
        freq="D",
    )

    for series_index in range(3):
        phase = series_index * 0.4

        for index, ds in enumerate(dates):
            value = (
                10.0
                + 2.0 * math.sin(index / 5.0 + phase)
                + 0.5 * math.cos(index / 11.0)
                + 0.01 * index
                + rng.normal(0.0, 0.05)
            )

            rows.append(
                {
                    "unique_id": f"series_{series_index}",
                    "ds": ds,
                    "y": float(value),
                }
            )

    return pd.DataFrame(rows)


def trainer_kwargs() -> dict[str, Any]:
    return {
        "accelerator": "gpu",
        "devices": 1,
        "enable_progress_bar": False,
        "enable_model_summary": False,
        "logger": False,
        "enable_checkpointing": False,
        "val_check_steps": MAX_STEPS,
    }


def build_models() -> list[tuple[str, Any]]:
    common = {
        "h": HORIZON,
        "input_size": INPUT_SIZE,
        "max_steps": MAX_STEPS,
        "random_seed": SEED,
        "loss": MAE(),
        "valid_loss": MAE(),
        **trainer_kwargs(),
    }

    return [
        (
            "DLinear",
            DLinear(
                moving_avg_window=3,
                alias="cert_DLinear",
                **common,
            ),
        ),
        (
            "NLinear",
            NLinear(
                alias="cert_NLinear",
                **common,
            ),
        ),
        (
            "MLP",
            MLP(
                hidden_size=32,
                num_layers=1,
                alias="cert_MLP",
                **common,
            ),
        ),
        (
            "NHITS",
            NHITS(
                n_blocks=[1, 1, 1],
                mlp_units=[
                    [32, 32],
                    [32, 32],
                    [32, 32],
                ],
                n_pool_kernel_size=[2, 2, 1],
                n_freq_downsample=[4, 2, 1],
                alias="cert_NHITS",
                **common,
            ),
        ),
        (
            "NBEATS",
            NBEATS(
                stack_types=["identity"],
                n_blocks=[1],
                mlp_units=[[32, 32]],
                alias="cert_NBEATS",
                **common,
            ),
        ),
        (
            "PatchTST",
            PatchTST(
                hidden_size=16,
                n_heads=4,
                patch_len=8,
                stride=4,
                encoder_layers=1,
                alias="cert_PatchTST",
                **common,
            ),
        ),
    ]


def collect_tensor_devices(value: Any) -> set[str]:
    devices: set[str] = set()

    if isinstance(value, torch.Tensor):
        devices.add(str(value.device))

    elif isinstance(value, dict):
        for item in value.values():
            devices.update(collect_tensor_devices(item))

    elif isinstance(value, (list, tuple)):
        for item in value:
            devices.update(collect_tensor_devices(item))

    return devices


def parameter_devices(model: Any) -> list[str]:
    return sorted({str(parameter.device) for parameter in model.parameters()})


def certify_one(
    name: str,
    model: Any,
    data: pd.DataFrame,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "forward_calls": 0,
        "forward_parameter_devices": set(),
        "forward_input_devices": set(),
        "cuda_forward_confirmed": False,
    }

    def forward_pre_hook(
        module: Any,
        args: tuple[Any, ...],
    ) -> None:
        evidence["forward_calls"] += 1

        current_parameter_devices = {str(parameter.device) for parameter in module.parameters()}

        current_input_devices = collect_tensor_devices(args)

        evidence["forward_parameter_devices"].update(current_parameter_devices)

        evidence["forward_input_devices"].update(current_input_devices)

        if any(device.startswith("cuda") for device in current_parameter_devices) or any(
            device.startswith("cuda") for device in current_input_devices
        ):
            evidence["cuda_forward_confirmed"] = True

    hook_handle = model.register_forward_pre_hook(forward_pre_hook)

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()

    memory_before = torch.cuda.memory_allocated()

    reserved_before = torch.cuda.memory_reserved()

    started = time.perf_counter()

    try:
        nf = NeuralForecast(
            models=[model],
            freq="D",
        )

        nf.fit(
            df=data,
            val_size=8,
        )

        torch.cuda.synchronize()
        fit_finished = time.perf_counter()

        predictions = nf.predict()

        torch.cuda.synchronize()
        finished = time.perf_counter()

    finally:
        hook_handle.remove()

    numeric = predictions.select_dtypes(include=[np.number])

    values = numeric.to_numpy(dtype=float)
    finite = bool(np.isfinite(values).all())

    prediction_path = PREDICTION_DIR / f"{name.lower()}_predictions.csv"

    predictions.to_csv(
        prediction_path,
        index=False,
    )

    peak_allocated = torch.cuda.max_memory_allocated()

    peak_reserved = torch.cuda.max_memory_reserved()

    post_run_devices = parameter_devices(model)

    record = {
        "model": name,
        "status": "PASS",
        "fit_seconds": fit_finished - started,
        "predict_seconds": finished - fit_finished,
        "total_seconds": finished - started,
        "prediction_rows": int(len(predictions)),
        "prediction_columns": list(predictions.columns),
        "prediction_finite": finite,
        "forward_calls": int(evidence["forward_calls"]),
        "forward_parameter_devices": sorted(evidence["forward_parameter_devices"]),
        "forward_input_devices": sorted(evidence["forward_input_devices"]),
        "cuda_forward_confirmed": bool(evidence["cuda_forward_confirmed"]),
        "post_run_parameter_devices": (post_run_devices),
        "cuda_memory_allocated_before": (memory_before),
        "cuda_memory_reserved_before": (reserved_before),
        "cuda_peak_memory_allocated": (peak_allocated),
        "cuda_peak_memory_reserved": (peak_reserved),
        "cuda_allocation_delta": (peak_allocated - memory_before),
        "prediction_file": str(prediction_path),
    }

    if not finite:
        raise RuntimeError(f"{name}: prediction contains non-finite values")

    if record["forward_calls"] <= 0:
        raise RuntimeError(f"{name}: no forward execution was observed")

    if not record["cuda_forward_confirmed"]:
        raise RuntimeError(f"{name}: CUDA forward execution was not confirmed")

    if peak_allocated <= memory_before:
        raise RuntimeError(f"{name}: no positive CUDA allocation delta detected")

    return record


def main() -> None:
    if not torch.cuda.is_available():
        raise SystemExit("CUDA_NOT_AVAILABLE")

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    PREDICTION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = make_data()
    results: list[dict[str, Any]] = []

    print("torch=", torch.__version__)
    print("torch_cuda=", torch.version.cuda)
    print(
        "device=",
        torch.cuda.get_device_name(0),
    )
    print("models=6")

    for name, model in build_models():
        print(f"START {name}")

        try:
            record = certify_one(
                name,
                model,
                data,
            )

            results.append(record)

            print(
                name,
                "PASS",
                "forward_calls=",
                record["forward_calls"],
                "peak_vram_mib=",
                round(
                    record["cuda_peak_memory_allocated"] / 1024**2,
                    2,
                ),
            )

        except Exception as exc:
            results.append(
                {
                    "model": name,
                    "status": "ERROR",
                    "error": repr(exc),
                    "traceback": (traceback.format_exc()),
                }
            )

            print(
                name,
                "ERROR",
                repr(exc),
            )

        finally:
            gc.collect()
            torch.cuda.empty_cache()

    passed = sum(item["status"] == "PASS" for item in results)

    failed = sum(item["status"] == "ERROR" for item in results)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_cuda_available": (torch.cuda.is_available()),
        "torch_version": torch.__version__,
        "torch_cuda_build": (torch.version.cuda),
        "gpu_name": (torch.cuda.get_device_name(0)),
        "horizon": HORIZON,
        "input_size": INPUT_SIZE,
        "max_steps": MAX_STEPS,
        "models": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
    }

    OUTPUT.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("models=", len(results))
    print("passed=", passed)
    print("failed=", failed)
    print("OUT=", OUTPUT)

    if failed:
        print("NF_FIT_PREDICT_GPU_PHASE1=PARTIAL")
        raise SystemExit(1)

    print("NF_FIT_PREDICT_GPU_PHASE1=PASS")


if __name__ == "__main__":
    main()

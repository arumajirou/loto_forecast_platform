#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM

from timer_formal_matrix_runner import (
    Game,
    TimeAxis,
    build_request,
    canonical_json,
    prediction_for_layout,
)

CANONICAL_GAME = Game.NUMBERS3
CANONICAL_AXIS = TimeAxis.DRAW_SEQUENCE
CANONICAL_HORIZON = 5
CANONICAL_LAYOUT = "position_panel_batched_univariate"
CANONICAL_SEED = 1
CUBLAS_WORKSPACE_CONFIG = ":4096:8"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--lock-sha256", required=True)
    parser.add_argument("--snapshot-manifest-sha256", required=True)
    parser.add_argument("--formal-runner-sha256", required=True)
    parser.add_argument("--replay-runner-sha256", required=True)
    parser.add_argument("--shell-sha256", required=True)
    parser.add_argument("--gpu-uuid", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()

    current_cublas = os.environ.get("CUBLAS_WORKSPACE_CONFIG")
    if current_cublas != CUBLAS_WORKSPACE_CONFIG:
        raise RuntimeError(
            f"CUBLAS_WORKSPACE_CONFIG must be {CUBLAS_WORKSPACE_CONFIG}, got {current_cublas!r}"
        )

    torch.manual_seed(CANONICAL_SEED)
    torch.set_grad_enabled(False)
    torch.use_deterministic_algorithms(True)

    if args.device == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but torch.cuda.is_available() is false")
        torch.cuda.set_device(0)
        torch.cuda.manual_seed_all(CANONICAL_SEED)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(0)
        target = torch.device("cuda:0")
    else:
        target = torch.device("cpu")

    request = build_request(
        game=CANONICAL_GAME,
        axis=CANONICAL_AXIS,
        horizon=CANONICAL_HORIZON,
        layout=CANONICAL_LAYOUT,
        seed=CANONICAL_SEED,
        device=args.device,
    )
    request_payload = request.model_dump(mode="json")
    request_json = canonical_json(request_payload)
    request_sha = sha256_bytes(request_json.encode("utf-8"))
    (args.out_dir / "request.json").write_text(request_json + "\n", encoding="utf-8")

    model = AutoModelForCausalLM.from_pretrained(
        str(args.snapshot.resolve()),
        trust_remote_code=True,
        local_files_only=True,
        torch_dtype=torch.float32,
    )
    model.eval()
    model.to(target)
    if args.device == "cuda":
        torch.cuda.synchronize(0)

    params = list(model.parameters())
    buffers = list(model.buffers())
    if not params:
        raise RuntimeError("Timer model has no parameters")
    effective_device = str(params[0].device)
    if args.device == "cuda" and not effective_device.startswith("cuda"):
        raise RuntimeError(f"model is not on CUDA: {effective_device}")
    if args.device == "cpu" and effective_device != "cpu":
        raise RuntimeError(f"model is not on CPU: {effective_device}")

    finite_parameters = all(bool(torch.isfinite(p).all().item()) for p in params)
    finite_buffers = all(bool(torch.isfinite(b).all().item()) for b in buffers if b.is_floating_point())
    if not finite_parameters or not finite_buffers:
        raise RuntimeError("non-finite model parameter/buffer detected")

    x = torch.tensor(request.series, dtype=torch.float32, device=target)
    input_raw = x.detach().to("cpu").contiguous().numpy().astype("<f4", copy=False).tobytes()
    input_sha = sha256_bytes(input_raw)

    with torch.inference_mode():
        y = prediction_for_layout(
            model,
            x,
            layout=CANONICAL_LAYOUT,
            horizon=CANONICAL_HORIZON,
        )
    if args.device == "cuda":
        torch.cuda.synchronize(0)

    expected_shape = (3, CANONICAL_HORIZON)
    if tuple(y.shape) != expected_shape:
        raise RuntimeError(f"output shape {tuple(y.shape)} != {expected_shape}")
    if not bool(torch.isfinite(y).all().item()):
        raise RuntimeError("non-finite replay prediction")
    if args.device == "cuda" and not str(y.device).startswith("cuda"):
        raise RuntimeError(f"CUDA output is on {y.device}")
    if args.device == "cpu" and str(y.device) != "cpu":
        raise RuntimeError(f"CPU output is on {y.device}")

    y_cpu = y.detach().to("cpu").contiguous().to(torch.float32)
    prediction_raw = y_cpu.numpy().astype("<f4", copy=False).tobytes()
    prediction_sha = sha256_bytes(prediction_raw)

    peak_allocated = 0
    peak_reserved = 0
    cuda_device_name = None
    if args.device == "cuda":
        peak_allocated = int(torch.cuda.max_memory_allocated(0))
        peak_reserved = int(torch.cuda.max_memory_reserved(0))
        cuda_device_name = torch.cuda.get_device_name(0)

    result = {
        "schema_version": "timer-base-84m.separate-process-replay-run.v1",
        "status": "PASS",
        "pid": os.getpid(),
        "game": CANONICAL_GAME.value,
        "time_axis": CANONICAL_AXIS.value,
        "horizon": CANONICAL_HORIZON,
        "target_layout": CANONICAL_LAYOUT,
        "seed": CANONICAL_SEED,
        "request_sha256": request_sha,
        "input_series_sha256_f32": input_sha,
        "prediction_sha256_f32": prediction_sha,
        "predictions": y_cpu.tolist(),
        "input_shape": list(x.shape),
        "output_shape": list(y.shape),
        "finite_predictions": True,
        "finite_parameters": finite_parameters,
        "finite_float_buffers": finite_buffers,
        "point_forecast": True,
        "chronology_mapping_sha256": request.chronology_evidence.mapping_sha256,
        "model_id": request.model_id,
        "repo_id": request.repo_id,
        "model_revision": request.model_revision,
        "weight_sha256": request.weight_sha256,
        "config_sha256": request.config_sha256,
        "snapshot_manifest_sha256": args.snapshot_manifest_sha256,
        "dependency_lock_sha256": args.lock_sha256,
        "source_head_sha": args.source_head,
        "formal_runner_sha256": args.formal_runner_sha256,
        "replay_runner_sha256": args.replay_runner_sha256,
        "shell_sha256": args.shell_sha256,
        "requested_device": args.device,
        "effective_device": effective_device,
        "input_device": str(x.device),
        "output_device": str(y.device),
        "model_on_cuda": effective_device.startswith("cuda"),
        "cpu_fallback": False,
        "gpu_uuid": args.gpu_uuid if args.device == "cuda" else None,
        "model_class": model.__class__.__name__,
        "parameter_count": sum(p.numel() for p in params),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "torch": torch.__version__,
        "torch_cuda_build": torch.version.cuda,
        "cuda_device_name": cuda_device_name,
        "torch_peak_memory_allocated_bytes": peak_allocated,
        "torch_peak_memory_reserved_bytes": peak_reserved,
        "cublas_workspace_config": current_cublas,
        "deterministic_algorithms": True,
        "network_policy": "HF/Transformers offline + local_files_only + Python socket deny guard",
        "synthetic_input_only": True,
        "holdout_accessed": False,
        "prospective_accessed": False,
        "serialized_model_state": False,
        "started_at_utc": started_at,
        "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (args.out_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

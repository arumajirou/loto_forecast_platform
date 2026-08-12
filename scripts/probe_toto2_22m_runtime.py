#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import traceback
from pathlib import Path
from typing import Any

import numpy as np

from loto.toto2_campaign.variant_probe import (
    TOTO2_22M_REPO_ID,
    TOTO2_22M_REQUIRED_FILES,
    TOTO2_22M_REVISION,
    VariantProbeError,
    capture_gpu_process,
    inspect_snapshot,
)

EXPECTED_MODEL_CLASS = "Toto2Model"
EXPECTED_TOTO_2_VERSION = "2.0.0"
EXPECTED_TOTO_MODELS_VERSION = "1.0.0"
EXPECTED_TORCH_VERSION_PREFIX = "2.13.0"
EXPECTED_CUDA_VERSION = "13.0"
EXPECTED_QUANTILES = tuple(round(index / 10, 1) for index in range(1, 10))


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_runtime_versions(torch: Any) -> dict[str, str | None]:
    versions: dict[str, str | None] = {
        "python": platform.python_version(),
        "torch": str(torch.__version__),
        "torch_cuda": str(torch.version.cuda) if torch.version.cuda else None,
        "toto_2": importlib.metadata.version("toto-2"),
        "toto_models": importlib.metadata.version("toto-models"),
        "huggingface_hub": importlib.metadata.version("huggingface-hub"),
    }
    if not str(versions["python"]).startswith("3.12."):
        raise VariantProbeError(f"Python 3.12.x required, got {versions['python']}")
    if not str(versions["torch"]).startswith(EXPECTED_TORCH_VERSION_PREFIX):
        raise VariantProbeError(f"Torch {EXPECTED_TORCH_VERSION_PREFIX} required")
    if versions["torch_cuda"] != EXPECTED_CUDA_VERSION:
        raise VariantProbeError(f"CUDA {EXPECTED_CUDA_VERSION} runtime required")
    if versions["toto_2"] != EXPECTED_TOTO_2_VERSION:
        raise VariantProbeError("toto-2 version differs from the reviewed package version")
    if versions["toto_models"] != EXPECTED_TOTO_MODELS_VERSION:
        raise VariantProbeError("toto-models version differs from the reviewed package version")
    return versions


def validate_model(model: Any) -> dict[str, Any]:
    model_class = type(model).__name__
    if model_class != EXPECTED_MODEL_CLASS:
        raise VariantProbeError(
            f"model class mismatch: expected {EXPECTED_MODEL_CLASS}, got {model_class}"
        )
    parameter_count = sum(int(parameter.numel()) for parameter in model.parameters())
    if parameter_count <= 0:
        raise VariantProbeError("model parameter count must be positive")
    patch_size = int(getattr(model.config, "patch_size", -1))
    if patch_size != 32:
        raise VariantProbeError(f"unexpected patch_size: {patch_size}")
    quantiles = tuple(round(float(value), 1) for value in model.output_head.knots)
    if quantiles != EXPECTED_QUANTILES:
        raise VariantProbeError(f"unexpected quantile knots: {quantiles}")
    return {
        "model_class": model_class,
        "parameter_count": parameter_count,
        "patch_size": patch_size,
        "quantile_levels": list(quantiles),
    }


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    from huggingface_hub import snapshot_download
    import torch
    from toto2 import Toto2Model

    versions = require_runtime_versions(torch)
    if not torch.cuda.is_available():
        raise VariantProbeError("CUDA is required for the Toto 2.0 22M runtime probe")

    snapshot_path = Path(
        snapshot_download(
            repo_id=TOTO2_22M_REPO_ID,
            revision=TOTO2_22M_REVISION,
            cache_dir=args.cache_dir,
            allow_patterns=list(TOTO2_22M_REQUIRED_FILES),
            local_files_only=args.local_files_only,
        )
    )
    snapshot = inspect_snapshot(snapshot_path)

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    device = torch.device("cuda:0")
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats(device)
    vram_before = int(torch.cuda.memory_allocated(device))

    model = Toto2Model.from_pretrained(str(snapshot_path))
    identity = validate_model(model)
    model = model.to(device).eval()
    model_device = str(next(model.parameters()).device)
    if not model_device.startswith("cuda"):
        raise VariantProbeError(f"model did not move to CUDA: {model_device}")

    context_length = 128
    horizon = 1
    variates = 3
    values = np.arange(context_length * variates, dtype=np.float32)
    values = (values % 10).reshape(1, variates, context_length)
    target = torch.as_tensor(values, dtype=torch.float32, device=device)
    inputs = {
        "target": target,
        "target_mask": torch.ones_like(target, dtype=torch.bool),
        "series_ids": torch.zeros((1, variates), dtype=torch.long, device=device),
    }

    with torch.inference_mode():
        output = model.forecast(
            inputs,
            horizon=horizon,
            decode_block_size=32,
            has_missing_values=False,
        )
    torch.cuda.synchronize(device)

    expected_shape = (9, 1, variates, horizon)
    actual_shape = tuple(int(value) for value in output.shape)
    if actual_shape != expected_shape:
        raise VariantProbeError(
            f"output shape mismatch: expected {expected_shape}, got {actual_shape}"
        )
    if not bool(torch.isfinite(output).all().item()):
        raise VariantProbeError("model output contains non-finite values")
    if not bool(((output[1:] - output[:-1]) >= -1e-6).all().item()):
        raise VariantProbeError("native quantiles are not monotonic")

    output_device = str(output.device)
    if not output_device.startswith("cuda"):
        raise VariantProbeError(f"output fell back to CPU: {output_device}")
    gpu_process = capture_gpu_process(os.getpid())
    peak_vram = int(torch.cuda.max_memory_allocated(device))
    if peak_vram <= 0:
        raise VariantProbeError("CUDA probe did not record positive peak VRAM")

    native = output.detach().to("cpu", dtype=torch.float32).numpy()
    output_path = args.output / "native_output.npy"
    np.save(output_path, native, allow_pickle=False)
    output_sha256 = sha256_bytes(native.tobytes(order="C"))

    return {
        "status": "PASS",
        "probe_contract": "toto2-22m-runtime-probe-v1",
        "repo_id": TOTO2_22M_REPO_ID,
        "revision": TOTO2_22M_REVISION,
        "pid": os.getpid(),
        "seed": args.seed,
        "local_files_only": args.local_files_only,
        "snapshot": snapshot,
        "runtime_versions": versions,
        "model_identity": identity,
        "device": {
            "requested": "cuda",
            "model": model_device,
            "output": output_device,
            "torch_device_name": torch.cuda.get_device_name(device),
            "gpu_uuid": gpu_process.gpu_uuid,
            "nvidia_smi_used_gpu_memory_mib": gpu_process.used_gpu_memory_mib,
            "vram_before_bytes": vram_before,
            "peak_vram_bytes": peak_vram,
            "cpu_fallback": False,
        },
        "input_shape": list(target.shape),
        "output_shape": list(actual_shape),
        "output_finite": True,
        "quantile_monotonicity": True,
        "native_output_path": str(output_path),
        "native_output_sha256": output_sha256,
        "snapshot_validation_ready_candidate": True,
        "formal_runtime_certified": False,
        "shared_routing_allowed": False,
        "accuracy_certified": False,
        "holdout_open": False,
        "prospective_open": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the pinned Toto 2.0 22M snapshot on CUDA")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--local-files-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = run_probe(args)
    except Exception as exc:
        result = {
            "status": "FAILED",
            "probe_contract": "toto2-22m-runtime-probe-v1",
            "pid": os.getpid(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "formal_runtime_certified": False,
            "shared_routing_allowed": False,
            "accuracy_certified": False,
        }
        atomic_json(args.output / "probe.json", result)
        print(json.dumps(result, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    atomic_json(args.output / "probe.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

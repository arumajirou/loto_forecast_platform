#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

MODEL_ID = "toto-2.0-4m"
REPO_ID = "Datadog/Toto-2.0-4m"
REVISION = "8306a9801cf98c0f5ffe4b2dcc8f496e616d84d9"
CODE_REVISION = "44ea4e88852228039564aa3e76fac26aafac0803"

SNAPSHOT = Path(f"/mnt/e/env/huggingface/hub/models--Datadog--Toto-2.0-4m/snapshots/{REVISION}")

EXPECTED_MODEL_SHA256 = "316660d5afb47943e531f39242e0b02ca0b8bb73be5709dfe07ca80dfce9805e"

EXPECTED_CONFIG_SHA256 = "7a926d130e401ab0c5fdb3564f46c8d917bd05c7b3ae26b9c22d2da2ef01d2d8"

BATCH_SIZE = 1
SERIES_COUNT = 7
CONTEXT_LENGTH = 512
HORIZON = 1
DECODE_BLOCK_SIZE = 32
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


def validate_snapshot() -> dict[str, Any]:
    if not SNAPSHOT.is_dir():
        raise RuntimeError(f"snapshot missing: {SNAPSHOT}")

    if SNAPSHOT.name != REVISION:
        raise RuntimeError("snapshot revision mismatch")

    files: dict[str, dict[str, Any]] = {}

    for name in (
        "README.md",
        "config.json",
        "model.safetensors",
    ):
        path = SNAPSHOT / name

        if not path.is_file():
            raise RuntimeError(f"required file missing: {path}")

        files[name] = {
            "path": str(path),
            "resolved_path": str(path.resolve()),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        }

    if files["config.json"]["sha256"] != EXPECTED_CONFIG_SHA256:
        raise RuntimeError("config.json SHA-256 mismatch")

    if files["model.safetensors"]["sha256"] != EXPECTED_MODEL_SHA256:
        raise RuntimeError("model.safetensors SHA-256 mismatch")

    return {
        "snapshot_path": str(SNAPSHOT),
        "revision": REVISION,
        "files": files,
    }


def invalid(message: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "INVALID_REQUEST",
        "model_id": MODEL_ID,
        "repo_id": REPO_ID,
        "revision": REVISION,
        "message": message,
    }


def run(request: dict[str, Any]) -> dict[str, Any]:
    try:
        import torch
        from toto2 import Toto2Model

        if request.get("model_id") != MODEL_ID:
            return invalid("model_id mismatch")

        if request.get("repo_id") != REPO_ID:
            return invalid("repo_id mismatch")

        if request.get("revision") != REVISION:
            return invalid("revision mismatch")

        if request.get("device") != "cuda":
            return invalid("device must be cuda")

        if request.get("local_files_only") is not True:
            return invalid("local_files_only must be true")

        artifact = validate_snapshot()

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable")

        torch.manual_seed(FIXED_SEED)
        torch.cuda.manual_seed_all(FIXED_SEED)
        torch.cuda.set_device(0)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(0)

        model = Toto2Model.from_pretrained(
            str(SNAPSHOT),
            local_files_only=True,
        )

        model = model.to("cuda").eval()

        target = torch.linspace(
            1.0,
            37.0,
            SERIES_COUNT * CONTEXT_LENGTH,
            device="cuda",
            dtype=torch.float32,
        ).reshape(
            BATCH_SIZE,
            SERIES_COUNT,
            CONTEXT_LENGTH,
        )

        target_mask = torch.ones_like(
            target,
            dtype=torch.bool,
        )

        series_ids = torch.arange(
            SERIES_COUNT,
            device="cuda",
            dtype=torch.long,
        ).reshape(
            BATCH_SIZE,
            SERIES_COUNT,
        )

        with torch.inference_mode():
            quantiles = model.forecast(
                {
                    "target": target,
                    "target_mask": target_mask,
                    "series_ids": series_ids,
                },
                horizon=HORIZON,
                decode_block_size=DECODE_BLOCK_SIZE,
                has_missing_values=False,
            )

        torch.cuda.synchronize(0)

        expected_shape = [
            9,
            BATCH_SIZE,
            SERIES_COUNT,
            HORIZON,
        ]

        if list(quantiles.shape) != expected_shape:
            raise RuntimeError(f"unexpected output shape: {list(quantiles.shape)}")

        if quantiles.device.type != "cuda":
            raise RuntimeError("output not on CUDA")

        if not torch.isfinite(quantiles).all():
            raise RuntimeError("non-finite output")

        parameter = next(model.parameters())

        if parameter.device.type != "cuda":
            raise RuntimeError(f"model not on CUDA: {parameter.device}")

        peak_vram_bytes = int(torch.cuda.max_memory_allocated(0))

        if peak_vram_bytes <= 0:
            raise RuntimeError("peak VRAM is not positive")

        median_predictions = quantiles[4, 0, :, 0].detach().cpu().tolist()

        return {
            "schema_version": 1,
            "status": "OK",
            "model_id": MODEL_ID,
            "repo_id": REPO_ID,
            "revision": REVISION,
            "code_revision": CODE_REVISION,
            "runtime_pid": os.getpid(),
            "input_shape": list(target.shape),
            "output_shape": list(quantiles.shape),
            "output_finite": True,
            "median_predictions": (median_predictions),
            "properties": {
                "model_class": (type(model).__name__),
                "model_parameter_count": sum(item.numel() for item in model.parameters()),
                "batch_size": BATCH_SIZE,
                "series_count": SERIES_COUNT,
                "context_length": CONTEXT_LENGTH,
                "horizon": HORIZON,
                "quantile_count": 9,
                "decode_block_size": (DECODE_BLOCK_SIZE),
                "runtime_certification_scope": ("FULL_INFERENCE"),
                "probabilistic_forecast_executed": (True),
                "native_domain_contract_used": True,
                "lottery_domain_compatibility_certified": (False),
                "forecast_accuracy_certified": False,
                "license": "Apache-2.0",
                "commercial_use": True,
                "personal_use": True,
                "artifact": artifact,
            },
            "runtime_environment": {
                "python_version": (sys.version.split()[0]),
                "toto_models_version": (importlib.metadata.version("toto-models")),
                "toto_2_version": (importlib.metadata.version("toto-2")),
                "torch_version": torch.__version__,
                "torch_cuda_version": (torch.version.cuda),
            },
            "gpu_evidence": {
                "requested_device": "cuda",
                "model_device": str(parameter.device),
                "output_device": str(quantiles.device),
                "runtime_gpu_used": True,
                "runtime_cpu_fallback": False,
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

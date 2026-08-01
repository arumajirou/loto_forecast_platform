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

import numpy as np
import pandas as pd

MODEL_ID = "kronos-base"
MODEL_REPO_ID = "NeoQuasar/Kronos-base"
MODEL_REVISION = "2b554741eca47781b64468546e77fef3e85130e6"

TOKENIZER_REPO_ID = "NeoQuasar/Kronos-Tokenizer-base"
TOKENIZER_REVISION = "0e0117387f39004a9016484a186a908917e22426"

KRONOS_CODE_REVISION = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"

MODEL_SNAPSHOT = Path(
    f"/mnt/e/env/huggingface/hub/models--NeoQuasar--Kronos-base/snapshots/{MODEL_REVISION}"
)

TOKENIZER_SNAPSHOT = Path(
    "/mnt/e/env/huggingface/hub/"
    "models--NeoQuasar--Kronos-Tokenizer-base/"
    "snapshots/"
    f"{TOKENIZER_REVISION}"
)

LOOKBACK = 128
PREDICTION_LENGTH = 4
MAX_CONTEXT = 512
FIXED_SEED = 42

EXPECTED_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def validate_snapshot(
    root: Path,
    revision: str,
    required_names: tuple[str, ...],
) -> dict[str, Any]:
    if not root.is_dir():
        raise RuntimeError(f"snapshot missing: {root}")

    if root.name != revision:
        raise RuntimeError(f"snapshot revision mismatch: expected={revision}, actual={root.name}")

    files: dict[str, dict[str, Any]] = {}

    for name in required_names:
        path = root / name

        if not path.is_file():
            raise RuntimeError(f"required snapshot file missing: {path}")

        files[name] = {
            "path": str(path),
            "resolved_path": str(path.resolve()),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        }

    return {
        "snapshot_path": str(root),
        "revision": revision,
        "files": files,
    }


def error_result(
    status: str,
    message: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": status,
        "model_id": MODEL_ID,
        "repo_id": MODEL_REPO_ID,
        "revision": MODEL_REVISION,
        "message": message,
    }


def run(request: dict[str, Any]) -> dict[str, Any]:
    try:
        import torch
        from model import (
            Kronos,
            KronosPredictor,
            KronosTokenizer,
        )

        if request.get("model_id") != MODEL_ID:
            return error_result(
                "INVALID_REQUEST",
                "model_id mismatch",
            )

        if request.get("repo_id") != MODEL_REPO_ID:
            return error_result(
                "INVALID_REQUEST",
                "repo_id mismatch",
            )

        if request.get("revision") != MODEL_REVISION:
            return error_result(
                "INVALID_REQUEST",
                "model revision mismatch",
            )

        if request.get("tokenizer_repo_id") != TOKENIZER_REPO_ID:
            return error_result(
                "INVALID_REQUEST",
                "tokenizer repo mismatch",
            )

        if request.get("tokenizer_revision") != TOKENIZER_REVISION:
            return error_result(
                "INVALID_REQUEST",
                "tokenizer revision mismatch",
            )

        if request.get("device") != "cuda":
            return error_result(
                "INVALID_REQUEST",
                "device must be cuda",
            )

        if request.get("local_files_only") is not True:
            return error_result(
                "INVALID_REQUEST",
                "local_files_only must be true",
            )

        model_artifact = validate_snapshot(
            MODEL_SNAPSHOT,
            MODEL_REVISION,
            (
                "README.md",
                "config.json",
                "model.safetensors",
            ),
        )

        tokenizer_artifact = validate_snapshot(
            TOKENIZER_SNAPSHOT,
            TOKENIZER_REVISION,
            (
                "README.md",
                "config.json",
                "model.safetensors",
            ),
        )

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable")

        torch.manual_seed(FIXED_SEED)
        torch.cuda.manual_seed_all(FIXED_SEED)
        np.random.seed(FIXED_SEED)

        torch.cuda.set_device(0)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(0)

        tokenizer = KronosTokenizer.from_pretrained(
            str(TOKENIZER_SNAPSHOT),
            local_files_only=True,
        )

        model = Kronos.from_pretrained(
            str(MODEL_SNAPSHOT),
            local_files_only=True,
        )

        predictor = KronosPredictor(
            model=model,
            tokenizer=tokenizer,
            device="cuda:0",
            max_context=MAX_CONTEXT,
        )

        timestamps = pd.date_range(
            start="2026-01-01T00:00:00",
            periods=LOOKBACK + PREDICTION_LENGTH,
            freq="h",
        )

        index = np.arange(
            LOOKBACK,
            dtype=np.float64,
        )

        base = (
            100.0
            + np.linspace(
                0.0,
                8.0,
                LOOKBACK,
                dtype=np.float64,
            )
            + np.sin(index / 8.0)
        )

        open_values = base
        close_values = base + 0.2 * np.cos(index / 5.0)
        high_values = (
            np.maximum(
                open_values,
                close_values,
            )
            + 0.5
        )
        low_values = (
            np.minimum(
                open_values,
                close_values,
            )
            - 0.5
        )
        volume_values = 1000.0 + index * 3.0
        amount_values = close_values * volume_values

        history = pd.DataFrame(
            {
                "open": open_values,
                "high": high_values,
                "low": low_values,
                "close": close_values,
                "volume": volume_values,
                "amount": amount_values,
            }
        )

        x_timestamp = pd.Series(
            timestamps[:LOOKBACK],
            name="timestamps",
        )

        y_timestamp = pd.Series(
            timestamps[LOOKBACK : LOOKBACK + PREDICTION_LENGTH],
            name="timestamps",
        )

        prediction = predictor.predict(
            df=history,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=PREDICTION_LENGTH,
            T=1.0,
            top_k=0,
            top_p=0.9,
            sample_count=1,
            verbose=False,
        )

        torch.cuda.synchronize(0)

        if list(prediction.shape) != [4, 6]:
            raise RuntimeError(f"unexpected prediction shape: {list(prediction.shape)}")

        if list(prediction.columns) != EXPECTED_COLUMNS:
            raise RuntimeError(f"unexpected prediction columns: {list(prediction.columns)}")

        values = prediction.to_numpy(dtype=np.float64)

        if not np.isfinite(values).all():
            raise RuntimeError("prediction contains non-finite values")

        model_parameter = next(model.parameters())
        tokenizer_parameter = next(tokenizer.parameters())

        if model_parameter.device.type != "cuda":
            raise RuntimeError(f"model not on CUDA: {model_parameter.device}")

        if tokenizer_parameter.device.type != "cuda":
            raise RuntimeError(f"tokenizer not on CUDA: {tokenizer_parameter.device}")

        peak_vram_bytes = int(torch.cuda.max_memory_allocated(0))

        if peak_vram_bytes <= 0:
            raise RuntimeError("peak VRAM is not positive")

        prediction_records = []

        for timestamp, row in prediction.iterrows():
            record = {
                "timestamp": str(timestamp),
            }

            for column in EXPECTED_COLUMNS:
                value = float(row[column])

                if not math.isfinite(value):
                    raise RuntimeError("non-finite prediction value")

                record[column] = value

            prediction_records.append(record)

        return {
            "schema_version": 1,
            "status": "OK",
            "model_id": MODEL_ID,
            "repo_id": MODEL_REPO_ID,
            "revision": MODEL_REVISION,
            "tokenizer_repo_id": TOKENIZER_REPO_ID,
            "tokenizer_revision": TOKENIZER_REVISION,
            "kronos_code_revision": (KRONOS_CODE_REVISION),
            "runtime_pid": os.getpid(),
            "prediction_shape": list(prediction.shape),
            "prediction_columns": list(prediction.columns),
            "prediction_records": prediction_records,
            "output_finite": True,
            "properties": {
                "model_class": type(model).__name__,
                "tokenizer_class": (type(tokenizer).__name__),
                "predictor_class": (type(predictor).__name__),
                "model_parameter_count": sum(parameter.numel() for parameter in model.parameters()),
                "tokenizer_parameter_count": sum(
                    parameter.numel() for parameter in tokenizer.parameters()
                ),
                "lookback": LOOKBACK,
                "prediction_length": (PREDICTION_LENGTH),
                "max_context": MAX_CONTEXT,
                "native_domain": ("financial_ohlcv_kline"),
                "runtime_certification_scope": ("FULL_INFERENCE"),
                "tokenizer_executed": True,
                "autoregressive_forecast_executed": (True),
                "native_domain_contract_used": True,
                "lottery_domain_compatibility_certified": (False),
                "forecast_accuracy_certified": False,
                "license": "MIT",
                "commercial_use": True,
                "model_artifact": model_artifact,
                "tokenizer_artifact": (tokenizer_artifact),
            },
            "gpu_evidence": {
                "requested_device": "cuda",
                "model_device": str(model_parameter.device),
                "tokenizer_device": str(tokenizer_parameter.device),
                "runtime_gpu_used": True,
                "runtime_cpu_fallback": False,
                "peak_vram_bytes": peak_vram_bytes,
                "gpu_pid": os.getpid(),
            },
        }

    except Exception as exc:
        return {
            "schema_version": 1,
            "status": "ERROR",
            "model_id": MODEL_ID,
            "repo_id": MODEL_REPO_ID,
            "revision": MODEL_REVISION,
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

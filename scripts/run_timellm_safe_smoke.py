#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from loto.game.geometry import geometry_for, known_games


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a reduced, evidence-producing TimeLLM GPU runtime smoke."
    )
    parser.add_argument("--game", choices=known_games(), default="numbers4")
    parser.add_argument("--rows", type=int, default=160)
    parser.add_argument("--max-steps", type=int, default=5)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--output", required=True)
    parser.add_argument("--llm", default="openai-community/gpt2")
    parser.add_argument("--precision", default="bf16-mixed")
    parser.add_argument("--input-size", type=int, default=32)
    parser.add_argument("--windows-batch-size", type=int, default=8)
    return parser


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _nvidia_smi() -> str:
    try:
        proc = subprocess.run(
            ["nvidia-smi"], capture_output=True, text=True, timeout=5, check=False
        )
        return proc.stdout + proc.stderr
    except Exception as exc:  # evidence collection must not hide model outcome
        return f"nvidia-smi unavailable: {type(exc).__name__}: {exc}\n"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _synthetic_frame(game: str, rows: int) -> pd.DataFrame:
    geometry = geometry_for(game)
    payload: list[dict[str, Any]] = []
    span = geometry.value_max - geometry.value_min + 1
    for position in range(geometry.positions):
        for index in range(rows):
            value = geometry.value_min + ((index * 7 + position * 3 + 3) % span)
            payload.append(
                {
                    "unique_id": f"{game}-position-{position + 1}",
                    "ds": index + 1,
                    "y": float(value),
                }
            )
    return pd.DataFrame(payload)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.rows < 40:
        raise SystemExit("--rows must be >= 40")
    if args.max_steps < 1:
        raise SystemExit("--max-steps must be >= 1")

    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"refusing to reuse TimeLLM smoke output: {output}")
    output.mkdir(parents=True)

    config = {
        "execution_contract": "timellm-reduced-gpu-runtime-smoke-v1",
        "game": args.game,
        "rows": args.rows,
        "h": 1,
        "llm": args.llm,
        "precision": args.precision,
        "input_size": args.input_size,
        "batch_size": 1,
        "valid_batch_size": 1,
        "windows_batch_size": args.windows_batch_size,
        "inference_windows_batch_size": args.windows_batch_size,
        "d_ff": 64,
        "d_model": 16,
        "n_heads": 4,
        "max_steps": args.max_steps,
        "val_check_steps": 1,
        "random_seed": args.seed,
        "accelerator": "gpu",
        "devices": 1,
        "holdout_evaluated": False,
        "prospective_evaluated": False,
        "accuracy_evaluated": False,
        "promotion": False,
    }
    _atomic_json(output / "CONFIG.json", config)
    (output / "nvidia_smi_before.txt").write_text(_nvidia_smi(), encoding="utf-8")

    environment = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "pid": os.getpid(),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }
    _atomic_json(output / "ENVIRONMENT.json", environment)
    if not torch.cuda.is_available():
        _atomic_json(
            output / "RESULT.json",
            {
                "status": "GPU_UNAVAILABLE",
                "runtime_smoke": False,
                "game_compatibility": "NOT_TESTED",
            },
        )
        return 2

    from neuralforecast import NeuralForecast
    from neuralforecast.models import TimeLLM

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    torch.set_float32_matmul_precision("high")

    frame = _synthetic_frame(args.game, args.rows)
    model = TimeLLM(
        h=1,
        input_size=args.input_size,
        llm=args.llm,
        llm_output_attention=False,
        llm_output_hidden_states=False,
        d_ff=64,
        d_model=16,
        n_heads=4,
        batch_size=1,
        valid_batch_size=1,
        windows_batch_size=args.windows_batch_size,
        inference_windows_batch_size=args.windows_batch_size,
        max_steps=args.max_steps,
        val_check_steps=1,
        random_seed=args.seed,
        accelerator="gpu",
        devices=1,
        precision=args.precision,
        enable_checkpointing=False,
        logger=False,
    )
    nf = NeuralForecast(models=[model], freq=1)

    started = time.perf_counter()
    nf.fit(df=frame, val_size=8)
    fit_seconds = time.perf_counter() - started
    prediction = nf.predict().reset_index(drop=True)
    value_columns = [column for column in prediction.columns if column not in {"unique_id", "ds"}]
    if not value_columns:
        raise RuntimeError("TimeLLM prediction did not expose a value column")
    value_col = value_columns[0]
    values = prediction.sort_values("unique_id")[value_col].to_numpy(dtype=float)
    if values.shape != (geometry_for(args.game).positions,):
        raise RuntimeError(f"unexpected prediction shape: {values.shape}")
    if not np.isfinite(values).all():
        raise RuntimeError("TimeLLM prediction contains NaN or Inf")

    torch.cuda.synchronize()
    geometry = geometry_for(args.game)
    raw_domain_ok = bool(
        np.all(values >= geometry.value_min) and np.all(values <= geometry.value_max)
    )
    prediction.to_csv(output / "PREDICTIONS.csv", index=False)
    (output / "nvidia_smi_after.txt").write_text(_nvidia_smi(), encoding="utf-8")

    result = {
        "status": "RUNTIME_SMOKE_SUCCEEDED",
        "runtime_smoke": True,
        "load": "PASS",
        "fit": "PASS",
        "predict": "PASS",
        "finite_output": True,
        "prediction_shape": list(values.shape),
        "fit_seconds": fit_seconds,
        "cuda_peak_allocated_mib": torch.cuda.max_memory_allocated() / 1024**2,
        "cuda_peak_reserved_mib": torch.cuda.max_memory_reserved() / 1024**2,
        "raw_game_domain": "PASS" if raw_domain_ok else "FAIL",
        "game_compatibility": "PENDING_DECODE_OR_CALIBRATION" if not raw_domain_ok else "RAW_DOMAIN_PASS",
        "accuracy_evaluated": False,
        "holdout_evaluated": False,
        "prospective_evaluated": False,
        "promotion": False,
        "execution_contract": config["execution_contract"],
    }
    _atomic_json(output / "RESULT.json", result)

    checksum_lines = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            checksum_lines.append(f"{_sha256(path)}  {path.name}")
    (output / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

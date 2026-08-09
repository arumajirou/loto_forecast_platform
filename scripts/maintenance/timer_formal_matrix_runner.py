#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import socket
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _deny_network(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError("NETWORK_ACCESS_BLOCKED_BY_TIMER_FORMAL_MATRIX")


socket.create_connection = _deny_network
socket.socket.connect = _deny_network

import torch
import transformers
from transformers import AutoModelForCausalLM

from loto.adapters.timer_base_84m.contracts import ArtifactPaths, ChronologyEvidence, TimerRequest
from loto.timer_base_84m_campaign.chronology import TimeAxis, validate_chronology
from loto.timer_base_84m_campaign.geometry import Game, geometry_for
from loto.timer_base_84m_campaign.provenance import (
    CONFIG_SHA256,
    LICENSE,
    MODEL_ID,
    MODEL_REVISION,
    OBSERVED_SOURCE_HEAD,
    REPO_ID,
    SOURCE_REVISION,
    TRANSFORMERS_VERSION,
    WEIGHT_SHA256,
)

GAMES = (Game.NUMBERS3, Game.NUMBERS4, Game.MINILOTO, Game.LOTO6, Game.LOTO7)
AXES = (TimeAxis.DRAW_SEQUENCE, TimeAxis.CALENDAR_TIME)
HORIZONS = (1, 2, 5)
LAYOUTS = ("position_univariate", "position_panel_batched_univariate")
SEEDS = (1, 7)
CONTEXT_LENGTH = 96


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def calendar_dates(game: Game, count: int) -> tuple[date, ...]:
    weekdays = geometry_for(game).draw_weekdays
    current = date(2024, 1, 1)
    values: list[date] = []
    while len(values) < count:
        if current.weekday() in weekdays:
            values.append(current)
        current += timedelta(days=1)
    return tuple(values)


def chronology_for(game: Game, axis: TimeAxis) -> ChronologyEvidence:
    draw_numbers = tuple(range(1, CONTEXT_LENGTH + 1))
    if axis is TimeAxis.CALENDAR_TIME:
        dates = calendar_dates(game, CONTEXT_LENGTH)
    else:
        start = date(2024, 1, 1)
        dates = tuple(start + timedelta(days=i) for i in range(CONTEXT_LENGTH))
    mapping = validate_chronology(
        game=game,
        time_axis=axis,
        draw_numbers=draw_numbers,
        dates=dates,
        cutoff_draw_no=draw_numbers[-1],
        cutoff_date=dates[-1],
        actuals_used=False,
    )
    return ChronologyEvidence(
        time_axis=axis,
        cutoff_draw_no=draw_numbers[-1],
        cutoff_date=dates[-1],
        draw_numbers=draw_numbers,
        dates=dates,
        mapping_sha256=mapping,
        future_actuals_present=False,
        duplicate_free=True,
        strictly_increasing=True,
        gap_free=True,
    )


def synthetic_series(game: Game, axis: TimeAxis, seed: int) -> tuple[tuple[float, ...], ...]:
    geometry = geometry_for(game)
    game_index = GAMES.index(game) + 1
    axis_index = AXES.index(axis)
    rows: list[tuple[float, ...]] = []
    for position in range(geometry.position_count):
        values: list[float] = []
        for t in range(CONTEXT_LENGTH):
            value = (
                math.sin(((t + 1) * (position + 1)) / 19.0 + seed * 0.001)
                + math.cos((t + 1) / 37.0)
                + game_index * 0.125
                + axis_index * 0.03125
            )
            values.append(float(value))
        rows.append(tuple(values))
    return tuple(rows)


def build_request(*, game: Game, axis: TimeAxis, horizon: int, layout: str, seed: int, device: str) -> TimerRequest:
    geometry = geometry_for(game)
    series = synthetic_series(game, axis, seed)
    case_id = f"{device}-{game.value}-{axis.value}-h{horizon}-{layout}-s{seed}"
    payload = {
        "schema_version": "timer-base-84m.request.v1",
        "run_id": case_id,
        "operation": "predict",
        "model_id": MODEL_ID,
        "repo_id": REPO_ID,
        "package_version": TRANSFORMERS_VERSION,
        "source_revision": SOURCE_REVISION,
        "observed_source_head": OBSERVED_SOURCE_HEAD,
        "model_revision": MODEL_REVISION,
        "config_sha256": CONFIG_SHA256,
        "weight_sha256": WEIGHT_SHA256,
        "license": LICENSE,
        "game": game,
        "target_layout": layout,
        "context_length": CONTEXT_LENGTH,
        "prediction_length": horizon,
        "seed": seed,
        "requested_device": device,
        "input_shape": (geometry.position_count, CONTEXT_LENGTH),
        "series": series,
        "past_covariates": None,
        "known_future_covariates": None,
        "chronology_evidence": chronology_for(game, axis),
        "actuals_used": False,
        "artifact_paths": ArtifactPaths(
            request_path="matrix/requests.jsonl",
            response_path="matrix/results.jsonl",
            snapshot_path="snapshot",
            manifest_path="matrix/manifest.json",
        ),
    }
    return TimerRequest.model_validate(payload)


def prediction_for_layout(model: torch.nn.Module, x: torch.Tensor, *, layout: str, horizon: int) -> torch.Tensor:
    if layout == "position_panel_batched_univariate":
        return model.generate(x, max_new_tokens=horizon)
    outputs: list[torch.Tensor] = []
    for index in range(x.shape[0]):
        outputs.append(model.generate(x[index : index + 1], max_new_tokens=horizon))
    return torch.cat(outputs, dim=0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--lock-sha256", required=True)
    parser.add_argument("--snapshot-manifest-sha256", required=True)
    parser.add_argument("--runner-sha256", required=True)
    parser.add_argument("--shell-sha256", required=True)
    parser.add_argument("--gpu-uuid", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    requests_path = args.out_dir / f"{args.device}-requests.jsonl"
    results_path = args.out_dir / f"{args.device}-results.jsonl"
    summary_path = args.out_dir / f"{args.device}-summary.raw.json"

    started_at = datetime.now(timezone.utc).isoformat()
    torch.manual_seed(1)
    torch.set_grad_enabled(False)
    torch.use_deterministic_algorithms(True, warn_only=True)

    if args.device == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but torch.cuda.is_available() is false")
        torch.cuda.set_device(0)
        torch.cuda.manual_seed_all(1)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(0)
        target = torch.device("cuda:0")
    else:
        target = torch.device("cpu")

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
    parameter_count = sum(p.numel() for p in params)
    effective_device = str(params[0].device) if params else str(target)
    finite_parameters = all(bool(torch.isfinite(p).all().item()) for p in params)
    finite_buffers = all(bool(torch.isfinite(b).all().item()) for b in buffers if b.is_floating_point())
    if not finite_parameters or not finite_buffers:
        raise RuntimeError("non-finite model parameter/buffer detected")
    if args.device == "cuda" and not effective_device.startswith("cuda"):
        raise RuntimeError(f"model is not on CUDA: {effective_device}")
    if args.device == "cpu" and effective_device != "cpu":
        raise RuntimeError(f"model is not on CPU: {effective_device}")

    model_class = model.__class__.__name__
    provider_pid = os.getpid()
    case_count = 0
    request_hashes: list[str] = []
    prediction_hashes: list[str] = []

    with requests_path.open("w", encoding="utf-8") as requests_file, results_path.open("w", encoding="utf-8") as results_file:
        for game in GAMES:
            geometry = geometry_for(game)
            series_ids = [f"{game.value}:position:{i + 1}" for i in range(geometry.position_count)]
            for axis in AXES:
                for horizon in HORIZONS:
                    for layout in LAYOUTS:
                        for seed in SEEDS:
                            case_started = datetime.now(timezone.utc).isoformat()
                            request = build_request(
                                game=game,
                                axis=axis,
                                horizon=horizon,
                                layout=layout,
                                seed=seed,
                                device=args.device,
                            )
                            request_payload = request.model_dump(mode="json")
                            request_json = canonical_json(request_payload)
                            request_sha = sha256_bytes(request_json.encode("utf-8"))
                            requests_file.write(request_json + "\n")

                            torch.manual_seed(seed)
                            if args.device == "cuda":
                                torch.cuda.manual_seed_all(seed)
                            x = torch.tensor(request.series, dtype=torch.float32, device=target)
                            input_raw = x.detach().to("cpu").contiguous().numpy().astype("<f4", copy=False).tobytes()
                            input_sha = sha256_bytes(input_raw)

                            with torch.inference_mode():
                                y = prediction_for_layout(model, x, layout=layout, horizon=horizon)
                            if args.device == "cuda":
                                torch.cuda.synchronize(0)

                            expected_shape = (geometry.position_count, horizon)
                            if tuple(y.shape) != expected_shape:
                                raise RuntimeError(f"{request.run_id}: output shape {tuple(y.shape)} != {expected_shape}")
                            if not bool(torch.isfinite(y).all().item()):
                                raise RuntimeError(f"{request.run_id}: non-finite prediction")
                            if args.device == "cuda" and not str(y.device).startswith("cuda"):
                                raise RuntimeError(f"{request.run_id}: CUDA output is on {y.device}")
                            if args.device == "cpu" and str(y.device) != "cpu":
                                raise RuntimeError(f"{request.run_id}: CPU output is on {y.device}")

                            y_cpu = y.detach().to("cpu").contiguous().to(torch.float32)
                            prediction_raw = y_cpu.numpy().astype("<f4", copy=False).tobytes()
                            prediction_sha = sha256_bytes(prediction_raw)
                            predictions = y_cpu.tolist()
                            result = {
                                "schema_version": "timer-base-84m.formal-matrix-case.v1",
                                "status": "PASS",
                                "case_id": request.run_id,
                                "game": game.value,
                                "time_axis": axis.value,
                                "horizon": horizon,
                                "target_layout": layout,
                                "seed": seed,
                                "context_length": CONTEXT_LENGTH,
                                "series_ids": series_ids,
                                "input_shape": list(x.shape),
                                "output_shape": list(y.shape),
                                "finite_predictions": True,
                                "point_forecast": True,
                                "predictions": predictions,
                                "input_series_sha256_f32": input_sha,
                                "prediction_sha256_f32": prediction_sha,
                                "request_sha256": request_sha,
                                "chronology_mapping_sha256": request.chronology_evidence.mapping_sha256,
                                "actuals_used": False,
                                "holdout_accessed": False,
                                "prospective_accessed": False,
                                "model_id": MODEL_ID,
                                "repo_id": REPO_ID,
                                "model_revision": MODEL_REVISION,
                                "weight_sha256": WEIGHT_SHA256,
                                "config_sha256": CONFIG_SHA256,
                                "snapshot_manifest_sha256": args.snapshot_manifest_sha256,
                                "dependency_lock_sha256": args.lock_sha256,
                                "source_head_sha": args.source_head,
                                "runner_sha256": args.runner_sha256,
                                "shell_sha256": args.shell_sha256,
                                "requested_device": args.device,
                                "effective_device": effective_device,
                                "model_on_cuda": effective_device.startswith("cuda"),
                                "input_device": str(x.device),
                                "output_device": str(y.device),
                                "provider_pid": provider_pid,
                                "cpu_fallback": False,
                                "gpu_uuid": args.gpu_uuid if args.device == "cuda" else None,
                                "case_started_at_utc": case_started,
                                "case_ended_at_utc": datetime.now(timezone.utc).isoformat(),
                            }
                            results_file.write(canonical_json(result) + "\n")
                            requests_file.flush()
                            results_file.flush()
                            case_count += 1
                            request_hashes.append(request_sha)
                            prediction_hashes.append(prediction_sha)

    expected_cases = len(GAMES) * len(AXES) * len(HORIZONS) * len(LAYOUTS) * len(SEEDS)
    if case_count != expected_cases:
        raise RuntimeError(f"case count mismatch: {case_count} != {expected_cases}")

    peak_allocated = 0
    peak_reserved = 0
    cuda_device_name = None
    if args.device == "cuda":
        torch.cuda.synchronize(0)
        peak_allocated = int(torch.cuda.max_memory_allocated(0))
        peak_reserved = int(torch.cuda.max_memory_reserved(0))
        cuda_device_name = torch.cuda.get_device_name(0)

    summary = {
        "schema_version": "timer-base-84m.formal-matrix-device-summary.v1",
        "status": "PASS",
        "device": args.device,
        "provider_pid": provider_pid,
        "case_count": case_count,
        "expected_case_count": expected_cases,
        "games": [g.value for g in GAMES],
        "time_axes": [a.value for a in AXES],
        "horizons": list(HORIZONS),
        "layouts": list(LAYOUTS),
        "seeds": list(SEEDS),
        "context_length": CONTEXT_LENGTH,
        "model_class": model_class,
        "parameter_count": parameter_count,
        "finite_parameters": finite_parameters,
        "finite_float_buffers": finite_buffers,
        "effective_device": effective_device,
        "cpu_fallback": False,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "torch": torch.__version__,
        "torch_cuda_build": torch.version.cuda,
        "transformers": transformers.__version__,
        "cuda_device_name": cuda_device_name,
        "gpu_uuid": args.gpu_uuid if args.device == "cuda" else None,
        "torch_peak_memory_allocated_bytes": peak_allocated,
        "torch_peak_memory_reserved_bytes": peak_reserved,
        "request_set_sha256": sha256_bytes("".join(request_hashes).encode("ascii")),
        "prediction_set_sha256": sha256_bytes("".join(prediction_hashes).encode("ascii")),
        "source_head_sha": args.source_head,
        "dependency_lock_sha256": args.lock_sha256,
        "snapshot_manifest_sha256": args.snapshot_manifest_sha256,
        "runner_sha256": args.runner_sha256,
        "shell_sha256": args.shell_sha256,
        "network_policy": "HF/Transformers offline + local_files_only + Python socket deny guard",
        "synthetic_contract_matrix": True,
        "holdout_accessed": False,
        "prospective_accessed": False,
        "started_at_utc": started_at,
        "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

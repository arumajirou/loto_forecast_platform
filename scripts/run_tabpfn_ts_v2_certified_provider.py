from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.adapters.tabpfn_ts.hash_gate import CheckpointGateSpec, verify_checkpoint_before_load
from loto.adapters.tabpfn_ts.manifests import CheckpointLane, require_executable_lane


def _load_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("request must be a JSON object")
    return payload


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _config_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _build_candidate_frame(history: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in history:
        selected = {int(record[f"n{position}"]) for position in range(1, 8)}
        draw_date = pd.Timestamp(record["draw_date"])
        if draw_date.tzinfo is not None:
            draw_date = draw_date.tz_convert(None)
        for candidate in range(1, 38):
            rows.append(
                {
                    "item_id": f"candidate-{candidate:02d}",
                    "timestamp": draw_date,
                    "target": float(candidate in selected),
                }
            )
    if not rows:
        raise ValueError("history must not be empty")
    return pd.DataFrame(rows).sort_values(["item_id", "timestamp"]).reset_index(drop=True)


def _collect_parameter_devices(root: object, torch_module: Any) -> list[str]:
    devices: set[str] = set()
    visited: set[int] = set()
    stack: list[object] = [root]
    while stack and len(visited) < 20_000:
        current = stack.pop()
        identity = id(current)
        if identity in visited:
            continue
        visited.add(identity)
        if isinstance(current, torch_module.nn.Module):
            devices.update(str(parameter.device) for parameter in current.parameters(recurse=True))
            continue
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, (list, tuple, set)):
            stack.extend(current)
        elif hasattr(current, "__dict__"):
            stack.extend(vars(current).values())
    return sorted(devices)


def _validate_request_identity(request: dict[str, Any]) -> tuple[str, int]:
    manifest = require_executable_lane(CheckpointLane.V2_REG_LEGACY)
    if request.get("repo_id") != manifest.repo_id:
        raise ValueError("unsupported repo_id for certified V2 lane")
    if request.get("revision") != manifest.revision:
        raise ValueError("unsupported revision for certified V2 lane")
    if request.get("weight_filename") != manifest.filename:
        raise ValueError("unsupported checkpoint filename for certified V2 lane")
    if request.get("local_files_only") is not True:
        raise ValueError("local_files_only must be true")
    if request.get("offline_required") is not True or request.get("network_access") is not False:
        raise ValueError("formal provider execution must be offline")
    if request.get("telemetry_disabled") is not True:
        raise ValueError("telemetry_disabled must be true")
    if request.get("license_accepted") is not True:
        raise ValueError("Prior Labs checkpoint license acceptance is required")
    if int(request.get("prediction_length", 1)) != 1:
        raise ValueError("legacy V2 certified provider requires prediction_length=1")
    device = str(request.get("device", "cuda"))
    if device not in {"cpu", "cuda"}:
        raise ValueError(f"unsupported device: {device}")
    return device, int(request.get("seed", 1))


def run_provider(request: dict[str, Any]) -> tuple[dict[str, Any], object | None]:
    os.environ.update(
        {
            "TABPFN_DISABLE_TELEMETRY": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "DO_NOT_TRACK": "1",
            "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
        }
    )
    requested_device, seed = _validate_request_identity(request)
    if requested_device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    snapshot_value = request.get("snapshot_path")
    if not snapshot_value:
        return {"status": "MODEL_WEIGHTS_MISSING", "message": "snapshot_path is required"}, None
    snapshot_path = Path(str(snapshot_value)).absolute()
    manifest = require_executable_lane(CheckpointLane.V2_REG_LEGACY)
    repository_cache_root = snapshot_path.parents[1]
    checkpoint_path = snapshot_path / manifest.filename
    try:
        checkpoint_evidence = verify_checkpoint_before_load(
            checkpoint_path=checkpoint_path,
            snapshot_path=snapshot_path,
            repository_cache_root=repository_cache_root,
            spec=CheckpointGateSpec(
                expected_filename=manifest.filename,
                expected_sha256=str(manifest.sha256),
                expected_revision=str(manifest.revision),
                local_files_only=True,
            ),
        )
    except Exception as exc:
        return {
            "status": "CHECKPOINT_HASH_MISMATCH",
            "message": str(exc),
            "error_type": type(exc).__name__,
        }, None

    import torch
    from tabpfn_time_series import TabPFNMode, TabPFNTSPipeline

    np.random.seed(seed)
    torch.manual_seed(seed)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    cuda_available = bool(torch.cuda.is_available())
    if requested_device == "cuda" and not cuda_available:
        return {
            "status": "FAILED_CPU_FALLBACK",
            "message": "CUDA was requested but torch.cuda.is_available() is false",
        }, None

    execution_device = requested_device
    if execution_device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    model_config = {"model_path": str(checkpoint_path)}
    pipeline = TabPFNTSPipeline(
        tabpfn_mode=TabPFNMode.LOCAL,
        tabpfn_model_config=model_config,
    )
    context_df = _build_candidate_frame(request["history"])
    predicted = pipeline.predict_df(context_df, prediction_length=1)

    scores = np.empty(37, dtype=float)
    for candidate in range(1, 38):
        item_id = f"candidate-{candidate:02d}"
        series = predicted.xs(item_id, level="item_id")["target"]
        scores[candidate - 1] = float(series.iloc[-1])
    if not np.isfinite(scores).all():
        raise ValueError("provider produced non-finite candidate scores")

    parameter_devices = _collect_parameter_devices(pipeline, torch)
    gpu_used = execution_device == "cuda"
    gpu_uuid = None
    gpu_name = None
    peak_vram_bytes = 0
    if gpu_used:
        torch.cuda.synchronize()
        device_index = torch.cuda.current_device()
        properties = torch.cuda.get_device_properties(device_index)
        gpu_name = str(properties.name)
        raw_uuid = getattr(properties, "uuid", None)
        gpu_uuid = str(raw_uuid) if raw_uuid is not None else None
        peak_vram_bytes = int(torch.cuda.max_memory_allocated(device_index))

    response = {
        "status": "OK",
        "schema_version": 1,
        "provider_version": 2,
        "repo_id": manifest.repo_id,
        "snapshot_path": str(snapshot_path),
        "predictions": scores.tolist(),
        "prediction_shape": [37],
        "finite": bool(all(math.isfinite(float(value)) for value in scores)),
        "properties": {
            "library": "tabpfn_time_series",
            "package": "tabpfn-time-series",
            "license": manifest.weight_license,
            "license_accepted": True,
            "backend": "torch",
            "context_length": int(len(request["history"])),
            "prediction_length": 1,
            "seed": seed,
            "weight_path": str(checkpoint_path),
            "weight_sha256": checkpoint_evidence.sha256,
            "verified_before_load": checkpoint_evidence.verified_before_load,
            "config_sha256": _config_sha256(model_config),
            "tabpfn_model_config": model_config,
            "offline_required": True,
            "telemetry_disabled": True,
        },
        "gpu_evidence": {
            "requested_device": requested_device,
            "execution_device": execution_device,
            "cuda_available": cuda_available,
            "gpu_requested": requested_device == "cuda",
            "gpu_used": gpu_used,
            "gpu_certification": "OBSERVED" if gpu_used else "NOT_CERTIFIED",
            "resource_certification": "GPU_PASS" if gpu_used else "CPU_ONLY_PASS",
            "cpu_fallback": False,
            "fallback_reason": None,
            "peak_vram_bytes": peak_vram_bytes,
            "gpu_pid": os.getpid() if gpu_used else None,
            "gpu_uuid_from_torch": gpu_uuid,
            "gpu_name": gpu_name,
            "model_parameter_devices": parameter_devices,
        },
        "artifact_reference": {
            "repo_id": manifest.repo_id,
            "revision": manifest.revision,
            "snapshot_path": str(snapshot_path),
            "checkpoint_path": str(checkpoint_path),
            "checkpoint_sha256": checkpoint_evidence.sha256,
        },
    }
    return response, pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the formally gated TabPFN-TS V2 provider")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path)
    parser.add_argument("--certification-hold-seconds", type=float, default=0.0)
    args = parser.parse_args()
    keepalive: object | None = None
    try:
        response, keepalive = run_provider(_load_payload(args.request))
    except Exception as exc:
        response = {"status": "ERROR", "error_type": type(exc).__name__, "message": str(exc)}
    _write_payload(args.response, response)
    if args.certification_hold_seconds > 0:
        time.sleep(args.certification_hold_seconds)
    del keepalive
    return 0 if response.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())

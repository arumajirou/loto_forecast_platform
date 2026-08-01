from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ID = "Prior-Labs/TabPFN-v2-reg"
REVISION = "4972a65a1b30806315c6f92499959ffbfc69a673"
WEIGHT_FILENAME = "tabpfn-v2-regressor.ckpt"


def _load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_candidate_frame(history: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in history:
        selected = {int(record[f"n{i}"]) for i in range(1, 8)}
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
    return pd.DataFrame(rows).sort_values(["item_id", "timestamp"]).reset_index(drop=True)


def run_provider(request: dict[str, Any]) -> dict[str, Any]:
    requested_device = str(request.get("device", "cpu"))
    if requested_device != "cuda":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    import torch
    from tabpfn_time_series import (
        TabPFNMode,
        TabPFNTSPipeline,
    )

    repo_id = str(request.get("repo_id", REPO_ID))
    revision = str(request.get("revision") or REVISION)
    weight_filename = str(request.get("weight_filename") or WEIGHT_FILENAME)
    local_files_only = bool(request.get("local_files_only", True))

    if repo_id != REPO_ID:
        return {
            "status": "PROVIDER_NOT_IMPLEMENTED",
            "message": f"unsupported repo_id: {repo_id}",
        }

    if revision != REVISION:
        return {
            "status": "PROVIDER_NOT_IMPLEMENTED",
            "message": f"unsupported revision: {revision}",
        }

    if not local_files_only:
        return {
            "status": "INVALID_REQUEST",
            "message": "local_files_only must be true",
        }

    snapshot_value = request.get("snapshot_path")

    if not snapshot_value:
        return {
            "status": "MODEL_WEIGHTS_MISSING",
            "message": "snapshot_path is required",
        }

    snapshot_path = Path(str(snapshot_value)).resolve()

    if snapshot_path.name != REVISION:
        return {
            "status": "MODEL_WEIGHTS_MISSING",
            "message": (f"snapshot directory does not match fixed revision: {snapshot_path}"),
        }

    if weight_filename != WEIGHT_FILENAME:
        return {
            "status": "INVALID_REQUEST",
            "message": (f"unsupported weight filename: {weight_filename}"),
        }

    # Keep the snapshot-visible path instead of resolving the final
    # Hugging Face symlink. Hub snapshots link their files to the
    # repository blobs directory, so resolving the file itself would
    # incorrectly appear to escape the snapshot.
    resolved_path = snapshot_path / WEIGHT_FILENAME

    if resolved_path.parent != snapshot_path:
        return {
            "status": "INVALID_REQUEST",
            "message": ("weight path escapes snapshot directory"),
        }

    cuda_available = torch.cuda.is_available()
    execution_device = "cuda" if requested_device == "cuda" and cuda_available else "cpu"
    if execution_device == "cuda":
        torch.cuda.reset_peak_memory_stats()

    if not resolved_path.is_file():
        return {
            "status": "MODEL_WEIGHTS_MISSING",
            "message": (f"fixed checkpoint not found: {resolved_path}"),
        }

    real_weight_path = resolved_path.resolve()
    repo_cache_root = snapshot_path.parents[1]
    blobs_root = (repo_cache_root / "blobs").resolve()

    try:
        real_weight_path.relative_to(blobs_root)
    except ValueError:
        return {
            "status": "INVALID_REQUEST",
            "message": (
                "checkpoint symlink target is outside "
                f"the fixed repository cache: {real_weight_path}"
            ),
        }

    tabpfn_model_config = {"model_path": str(resolved_path)}

    try:
        pipeline = TabPFNTSPipeline(
            tabpfn_mode=TabPFNMode.LOCAL, tabpfn_model_config=tabpfn_model_config
        )
    except Exception as exc:
        message = str(exc)
        if "license" in message.lower() or "gated" in message.lower():
            return {"status": "LICENSE_RESTRICTED", "message": message}
        raise

    history = request["history"]
    context_df = _build_candidate_frame(history)
    horizon = int(request.get("prediction_length", 1))

    try:
        predicted = pipeline.predict_df(context_df, prediction_length=horizon)
    except Exception as exc:
        message = str(exc)
        if "license" in message.lower() or "gated" in message.lower():
            return {"status": "LICENSE_RESTRICTED", "message": message}
        if "not found" in message.lower() or "no such file" in message.lower():
            return {"status": "MODEL_WEIGHTS_MISSING", "message": message}
        raise

    scores = np.empty(37, dtype=float)
    for candidate in range(1, 38):
        item_id = f"candidate-{candidate:02d}"
        series = predicted.xs(item_id, level="item_id")["target"]
        scores[candidate - 1] = float(series.iloc[-1])

    gpu_used = execution_device == "cuda"
    weight_sha256 = _sha256(resolved_path)
    config_bytes = json.dumps(tabpfn_model_config, sort_keys=True, default=str).encode()
    config_sha256 = hashlib.sha256(config_bytes).hexdigest()

    return {
        "status": "OK",
        "schema_version": 1,
        "provider_version": 1,
        "repo_id": repo_id,
        "snapshot_path": str(resolved_path.parent),
        "predictions": scores.tolist(),
        "prediction_shape": list(scores.shape),
        "finite": bool(np.isfinite(scores).all()),
        "properties": {
            "library": "tabpfn_time_series",
            "package": "tabpfn-time-series",
            "license": "Prior Labs License 1.1",
            "license_commercial_use": True,
            "license_attribution_required_on_distribution": True,
            "backend": "torch",
            "context_length": int(len(history)),
            "prediction_length": horizon,
            "weight_path": str(resolved_path),
            "weight_sha256": weight_sha256,
            "config_sha256": config_sha256,
            "tabpfn_model_config": tabpfn_model_config,
        },
        "gpu_evidence": {
            "requested_device": requested_device,
            "execution_device": execution_device,
            "cuda_available": cuda_available,
            "gpu_requested": requested_device == "cuda",
            "gpu_used": gpu_used,
            "gpu_certification": "OBSERVED" if gpu_used else "NOT_CERTIFIED",
            "resource_certification": "GPU_PASS" if gpu_used else "CPU_ONLY_PASS",
            "cpu_fallback": requested_device == "cuda" and not gpu_used,
            "fallback_reason": (
                None if execution_device == requested_device else "cuda_unavailable_or_not_selected"
            ),
            "peak_vram_bytes": int(torch.cuda.max_memory_allocated()) if gpu_used else 0,
            "gpu_pid": os.getpid() if gpu_used else None,
        },
        "artifact_reference": {
            "repo_id": repo_id,
            "revision": revision,
            "snapshot_path": str(resolved_path.parent),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TabPFN-TS provider in an isolated env")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path)
    args = parser.parse_args()
    try:
        response = run_provider(_load_payload(args.request))
    except Exception as exc:
        response = {"status": "ERROR", "error_type": type(exc).__name__, "message": str(exc)}
    _write_payload(args.response, response)


if __name__ == "__main__":
    main()

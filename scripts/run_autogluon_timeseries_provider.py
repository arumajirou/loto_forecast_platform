from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _history_to_long(history: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert legacy Loto7 draws to seven regular position series."""
    rows: list[dict[str, Any]] = []
    base_timestamp = pd.Timestamp("2000-01-01")

    for step, record in enumerate(history):
        timestamp = base_timestamp + pd.Timedelta(days=step)
        for position in range(1, 8):
            rows.append(
                {
                    "item_id": f"position-{position}",
                    "timestamp": timestamp,
                    "target": float(record[f"n{position}"]),
                }
            )

    return pd.DataFrame(rows).sort_values(["item_id", "timestamp"]).reset_index(drop=True)


def _run_provider_v1(request: dict[str, Any]) -> dict[str, Any]:
    requested_device = str(request.get("device", "cpu"))
    if requested_device != "cuda":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    import importlib.metadata as metadata

    import torch
    from autogluon.timeseries import TimeSeriesDataFrame, TimeSeriesPredictor

    mode = str(request.get("mode", "fit_predict_save"))
    artifact_dir = Path(request["artifact_dir"])
    prediction_length = int(request.get("prediction_length", 1))
    eval_metric = str(request.get("eval_metric", "MAE"))
    presets = str(request.get("presets", "fast_training"))
    time_limit = request.get("time_limit")
    seed = int(request.get("seed", 42))

    cuda_available = torch.cuda.is_available()

    if mode == "fit_predict_save":
        history = request.get("history") or []
        if not history:
            return {"status": "ERROR", "message": "fit_predict_save requires non-empty history"}
        frame = _history_to_long(history)
        ts = TimeSeriesDataFrame.from_data_frame(
            frame, id_column="item_id", timestamp_column="timestamp"
        )
        artifact_dir.mkdir(parents=True, exist_ok=True)
        predictor = TimeSeriesPredictor(
            prediction_length=prediction_length,
            target="target",
            eval_metric=eval_metric,
            freq="D",
            path=str(artifact_dir),
            verbosity=0,
        )
        try:
            predictor.fit(ts, presets=presets, time_limit=time_limit, random_seed=seed)
        except Exception as exc:
            message = str(exc)
            if "license" in message.lower() or "gated" in message.lower():
                return {"status": "LICENSE_RESTRICTED", "message": message}
            raise
        pred = predictor.predict(ts)
    elif mode == "load_predict":
        if not artifact_dir.exists() or not any(artifact_dir.iterdir()):
            return {
                "status": "ARTIFACT_MISSING",
                "message": f"artifact_dir not found or empty: {artifact_dir}",
            }
        history = request.get("history") or []
        if not history:
            return {"status": "ERROR", "message": "load_predict requires non-empty history"}
        frame = _history_to_long(history)
        ts = TimeSeriesDataFrame.from_data_frame(
            frame, id_column="item_id", timestamp_column="timestamp"
        )
        try:
            predictor = TimeSeriesPredictor.load(str(artifact_dir))
        except Exception as exc:
            return {"status": "ARTIFACT_MISSING", "message": f"failed to load predictor: {exc}"}
        pred = predictor.predict(ts)
    else:
        return {"status": "PROVIDER_NOT_IMPLEMENTED", "message": f"unsupported mode: {mode}"}

    reset = pred.reset_index().sort_values("item_id")
    values = reset["mean"].to_numpy(float)
    if len(values) != 7:
        return {
            "status": "PREDICTION_MISMATCH",
            "message": f"expected 7 position predictions, got {len(values)}",
        }

    execution_device = "cuda" if requested_device == "cuda" and cuda_available else "cpu"
    gpu_used = False

    try:
        library_version = metadata.version("autogluon.timeseries")
    except metadata.PackageNotFoundError:
        library_version = None

    return {
        "status": "OK",
        "schema_version": 1,
        "provider_version": 1,
        "mode": mode,
        "predictions": values.tolist(),
        "prediction_shape": list(values.shape),
        "finite": bool(np.isfinite(values).all()),
        "properties": {
            "library": "autogluon.timeseries",
            "package": "autogluon.timeseries",
            "library_version": library_version,
            "license": "Apache-2.0",
            "presets": presets,
            "time_limit": time_limit,
            "eval_metric": eval_metric,
            "prediction_length": prediction_length,
            "model_best": predictor.model_best,
            "model_names": predictor.model_names(),
        },
        "gpu_evidence": {
            "requested_device": requested_device,
            "execution_device": execution_device,
            "cuda_available": cuda_available,
            "gpu_requested": requested_device == "cuda",
            "gpu_used": gpu_used,
            "gpu_certification": "NOT_CERTIFIED",
            "resource_certification": "CPU_ONLY_PASS",
            "cpu_fallback": False,
            "fallback_reason": "fast_training_preset_is_cpu_only_statistical_and_tabular_ml",
        },
        "artifact_reference": {
            "artifact_dir": str(artifact_dir),
        },
    }


def run_provider(request: dict[str, Any]) -> dict[str, Any]:
    if request.get("schema_version") == 2:
        if str(SRC) not in sys.path:
            sys.path.insert(0, str(SRC))
        from loto.adapters.autogluon.provider import run_provider_v2

        return run_provider_v2(request)
    return _run_provider_v1(request)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run AutoGluon-TimeSeries provider in an isolated env"
    )
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path)
    args = parser.parse_args()
    request = _load_payload(args.request)
    try:
        response = run_provider(request)
    except Exception as exc:
        if request.get("schema_version") == 2:
            response = {
                "schema_version": 2,
                "provider_version": 2,
                "run_id": str(request.get("run_id") or "unknown-run"),
                "status": "ERROR",
                "operation": str(request.get("operation") or "discover"),
                "predictions": [],
                "model_inventory": [],
                "ensemble_inventory": [],
                "argument_ledger": [],
                "artifacts": {},
                "metadata": {},
                "runtime_evidence": None,
                "error": {
                    "code": "UNHANDLED_PROVIDER_EXCEPTION",
                    "phase": "main",
                    "message": str(exc),
                    "error_type": type(exc).__name__,
                },
            }
        else:
            response = {"status": "ERROR", "error_type": type(exc).__name__, "message": str(exc)}
    _write_payload(args.response, response)


if __name__ == "__main__":
    main()

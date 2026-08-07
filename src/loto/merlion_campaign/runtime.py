from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import numpy as np

from loto.merlion_campaign.artifacts import (
    build_model_manifest,
    resolve_under,
    verify_model_manifest,
)
from loto.merlion_campaign.protocol import PredictionPayload, ProviderRequest
from loto.merlion_campaign.time_adapter import compile_series


def _prediction_payload(forecast: Any, stderr: Any) -> PredictionPayload:
    forecast_frame = forecast.to_pd()
    if forecast_frame.shape[1] != 1:
        raise ValueError(f"expected one forecast column, got {forecast_frame.shape[1]}")
    values = forecast_frame.iloc[:, 0].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("forecast contains NaN or Inf")
    errors = None
    if stderr is not None:
        error_frame = stderr.to_pd()
        if error_frame.shape != forecast_frame.shape:
            raise ValueError("standard-error shape does not match forecast shape")
        error_values = error_frame.iloc[:, 0].to_numpy(dtype=float)
        if not np.isfinite(error_values).all() or (error_values < 0).any():
            raise ValueError("standard errors must be finite and non-negative")
        errors = error_values.tolist()
    return PredictionPayload(
        timestamps=[timestamp.isoformat() for timestamp in forecast_frame.index],
        values=values.tolist(),
        standard_errors=errors,
    )


def train_save(
    request: ProviderRequest,
    work_root: Path,
) -> tuple[PredictionPayload, dict[str, Any]]:
    from merlion.models.factory import ModelFactory
    from merlion.utils import TimeSeries

    if request.series is None or request.model_name is None:
        raise ValueError("train_save requires series and model_name")
    compiled = compile_series(request.series, request.time_semantics)
    model_config = dict(request.parameters)
    model_config.setdefault("max_forecast_steps", request.horizon)
    model = ModelFactory.create(request.model_name, **model_config)
    train_series = TimeSeries.from_pd(compiled.frame)
    model.train(train_series)
    forecast, stderr = model.forecast(request.horizon)
    prediction = _prediction_payload(forecast, stderr)
    if len(prediction.values) != request.horizon:
        raise ValueError("forecast horizon mismatch")

    model_dir = resolve_under(work_root, request.artifact_subdir)
    if model_dir.exists():
        shutil.rmtree(model_dir)
    model_dir.mkdir(parents=True, exist_ok=False)
    model.save(str(model_dir))
    manifest, manifest_sha = build_model_manifest(
        model_dir,
        request_id=request.request_id,
        model_name=request.model_name,
        config=model_config,
    )
    evidence = {
        "operation": "train_save",
        "process_id": os.getpid(),
        "model_name": request.model_name,
        "artifact_subdir": request.artifact_subdir,
        "model_manifest_sha256": manifest_sha,
        "artifact_file_count": len(manifest["files"]),
        "mapping_sha256": compiled.mapping_sha256,
        "time_semantics": request.time_semantics.value,
        "device": "cpu",
        "gpu_not_applicable": True,
        "cpu_fallback": False,
    }
    return prediction, evidence


def load_predict(
    request: ProviderRequest,
    work_root: Path,
) -> tuple[PredictionPayload, dict[str, Any]]:
    from merlion.models.factory import ModelFactory

    if request.model_name is None or request.expected_manifest_sha256 is None:
        raise ValueError("load_predict requires model_name and expected manifest hash")
    model_dir = resolve_under(work_root, request.artifact_subdir)
    manifest = verify_model_manifest(model_dir, request.expected_manifest_sha256)
    if manifest["model_name"] != request.model_name:
        raise ValueError("model name does not match trusted manifest")
    model = ModelFactory.load(request.model_name, str(model_dir))
    forecast, stderr = model.forecast(request.horizon)
    prediction = _prediction_payload(forecast, stderr)
    if len(prediction.values) != request.horizon:
        raise ValueError("forecast horizon mismatch after load")
    evidence = {
        "operation": "load_predict",
        "process_id": os.getpid(),
        "model_name": request.model_name,
        "artifact_subdir": request.artifact_subdir,
        "model_manifest_sha256": request.expected_manifest_sha256,
        "device": "cpu",
        "gpu_not_applicable": True,
        "cpu_fallback": False,
        "trusted_local_load": True,
    }
    return prediction, evidence

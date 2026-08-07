from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import numpy as np
import torch

from loto.adapters.tirex2.compat import schema_v1_to_v2
from loto.adapters.tirex2.contracts import (
    ArtifactReference,
    GpuEvidence,
    ModelIdentity,
    RuntimeEvidence,
    SeriesLayout,
    Tirex2Request,
    Tirex2Response,
)
from loto.tirex2_campaign.lock_review import validate_installed_review
from loto.tirex2_campaign.provenance import (
    MODEL_CONFIG_SHA256,
    MODEL_WEIGHT_SHA256,
    PACKAGE_VERSION,
    verify_model_snapshot,
)
from loto.tirex2_campaign.quantiles import normalize_forecast, point_forecast, quantile_mapping


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("request JSON must be an object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _trusted_cache_roots() -> list[Path]:
    roots: list[Path] = []
    for variable in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        value = os.environ.get(variable)
        if value:
            roots.append(Path(value))
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    roots.extend([hf_home, hf_home / "hub"])
    return [root for root in roots if root.exists()]


def _resolve_snapshot(request: Tirex2Request) -> Path:
    if request.snapshot_path is not None:
        return Path(request.snapshot_path)
    from huggingface_hub import snapshot_download

    return Path(
        snapshot_download(
            repo_id=request.repo_id,
            revision=request.revision,
            local_files_only=True,
            allow_patterns=["model.ckpt", "model-config.yaml", "LICENSE", "README.md"],
        )
    )


def _package_version() -> str:
    version = importlib.metadata.version("tirex-2")
    if version != PACKAGE_VERSION:
        raise RuntimeError(f"tirex-2 version mismatch: {version}; expected {PACKAGE_VERSION}")
    return version


def _tensor(values: list[list[float]], device: str) -> torch.Tensor:
    return torch.tensor(values, dtype=torch.float32, device=device)


def _covariate_tensor(block: Any, device: str) -> torch.Tensor | None:
    if block is None or not block.values:
        return None
    return _tensor(block.values, device)


def _timeseries_batch(
    request: Tirex2Request, device: str
) -> tuple[list[Any], dict[str, str | None]]:
    from tirex2 import TimeseriesType

    target = _tensor(request.target_history, device)
    past = _covariate_tensor(request.past_covariates, device)
    future = _covariate_tensor(request.future_covariates, device)
    evidence = {
        "target_tensor_device": str(target.device),
        "past_covariate_device": str(past.device) if past is not None else None,
        "future_covariate_device": str(future.device) if future is not None else None,
    }
    if request.series_layout == SeriesLayout.POSITION_JOINT_MULTIVARIATE:
        timeseries = TimeseriesType(
            target=target, past_covariates=past, future_covariates=future
        )
        return [timeseries], evidence
    rows: list[Any] = []
    for index in range(target.shape[0]):
        target_row = target[index : index + 1]
        rows.append(
            TimeseriesType(
                target=target_row, past_covariates=past, future_covariates=future
            )
        )
    return rows, evidence


def _normalize_batch(raw_forecasts: list[Any], request: Tirex2Request) -> np.ndarray:
    if request.series_layout == SeriesLayout.POSITION_JOINT_MULTIVARIATE:
        return normalize_forecast(
            np.asarray(raw_forecasts[0], dtype=np.float64),
            target_count=len(request.target_columns),
            prediction_length=request.prediction_length,
        )
    normalized = [
        normalize_forecast(
            np.asarray(raw, dtype=np.float64),
            target_count=1,
            prediction_length=request.prediction_length,
        )
        for raw in raw_forecasts
    ]
    return np.concatenate(normalized, axis=0)


def _model_parameter_device(model: Any) -> str | None:
    try:
        parameter = next(model.parameters())
    except (AttributeError, StopIteration, TypeError):
        return None
    return str(parameter.device)


def _gpu_uuid() -> str | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=uuid", "--format=csv,noheader"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines[torch.cuda.current_device()] if lines and torch.cuda.is_available() else None


def run_provider(request: Tirex2Request) -> Tirex2Response:
    validate_installed_review(
        environment_path=REPOSITORY_ROOT / "environments" / "tirex2-supported-py312",
        runtime_lane="tirex2-supported-py312",
    )
    from tirex2 import load_model

    _package_version()
    if request.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("FAILED_CPU_FALLBACK: CUDA requested but unavailable")
    snapshot_path = _resolve_snapshot(request).resolve(strict=True)
    verify_model_snapshot(snapshot_path, _trusted_cache_roots())
    if request.device == "cuda":
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        vram_before = int(torch.cuda.memory_allocated())
    else:
        vram_before = 0

    load_started = time.perf_counter()
    model = load_model(
        request.repo_id,
        device=request.device,
        hf_kwargs={"revision": request.revision, "local_files_only": True},
    )
    load_seconds = time.perf_counter() - load_started
    timeseries, tensor_evidence = _timeseries_batch(request, request.device)

    inference_started = time.perf_counter()
    raw_forecasts = model.forecast(
        timeseries,
        prediction_length=request.prediction_length,
        output_type="numpy",
    )
    if request.device == "cuda":
        torch.cuda.synchronize()
    inference_seconds = time.perf_counter() - inference_started
    forecasts = _normalize_batch(list(raw_forecasts), request)

    vram_peak = int(torch.cuda.max_memory_allocated()) if request.device == "cuda" else 0
    vram_after = int(torch.cuda.memory_allocated()) if request.device == "cuda" else 0
    response = Tirex2Response(
        run_id=request.run_id,
        model_identity=ModelIdentity(
            weight_sha256=MODEL_WEIGHT_SHA256,
            config_sha256=MODEL_CONFIG_SHA256,
        ),
        effective_arguments={
            "series_layout": request.series_layout.value,
            "context_length": request.context_length,
            "prediction_length": request.prediction_length,
            "target_count": len(request.target_columns),
            "quantile_levels": request.quantile_levels,
            "point_method": request.point_method,
            "local_files_only": request.local_files_only,
        },
        point_forecast=point_forecast(forecasts),
        quantiles=quantile_mapping(forecasts),
        series_identity=request.target_columns,
        prediction_index=list(range(1, request.prediction_length + 1)),
        runtime_evidence=RuntimeEvidence(
            provider_pid=os.getpid(),
            requested_device=request.device,
            effective_device=request.device,
            model_parameter_device=_model_parameter_device(model),
            target_tensor_device=str(tensor_evidence["target_tensor_device"]),
            past_covariate_device=tensor_evidence["past_covariate_device"],
            future_covariate_device=tensor_evidence["future_covariate_device"],
            output_tensor_device=None,
            dtype=request.dtype,
            cpu_fallback=False,
            load_time_seconds=load_seconds,
            inference_time_seconds=inference_seconds,
        ),
        gpu_evidence=GpuEvidence(
            gpu_uuid=_gpu_uuid() if request.device == "cuda" else None,
            external_pid_match=None,
            vram_before_bytes=vram_before,
            vram_peak_bytes=vram_peak,
            vram_after_bytes=vram_after,
        ),
        artifact_reference=ArtifactReference(snapshot_path=str(snapshot_path)),
    )
    return response


def parse_request(payload: dict[str, Any]) -> Tirex2Request:
    if payload.get("schema_version") == 2:
        return Tirex2Request.model_validate(payload)
    return schema_v1_to_v2(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the isolated TiRex-2 Contract v2 provider")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path)
    args = parser.parse_args()
    exit_code = 0
    try:
        response = run_provider(parse_request(_read_json(args.request))).model_dump(mode="json")
    except Exception as exc:
        response = {
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        exit_code = 1
    _write_json(args.response, response)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

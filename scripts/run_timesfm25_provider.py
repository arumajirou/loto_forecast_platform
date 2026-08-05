from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.adapters.timesfm25.contracts import (  # noqa: E402
    ArtifactReference,
    Backend,
    GPUExecutionEvidence,
    ModelIdentity,
    RuntimeEvidence,
    TimesFM25Request,
    TimesFM25Response,
)
from loto.timesfm25_campaign.backend_registry import BackendRegistry  # noqa: E402
from loto.timesfm25_campaign.forecast_config import (  # noqa: E402
    build_native_forecast_config,
    effective_argument_ledger,
)
from loto.timesfm25_campaign.model_manifest import load_default_manifest  # noqa: E402
from loto.timesfm25_campaign.quantiles import split_native_outputs  # noqa: E402
from loto.timesfm25_campaign.runtime import query_nvidia_process  # noqa: E402
from loto.timesfm25_campaign.serialization import sha256_file  # noqa: E402


def _load_request(path: Path) -> TimesFM25Request:
    return TimesFM25Request.model_validate_json(path.read_text(encoding="utf-8"))


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _find_torch_module(model: Any, torch: Any) -> Any | None:
    if isinstance(model, torch.nn.Module):
        return model
    for name in ("model", "_model", "module", "network"):
        candidate = getattr(model, name, None)
        if isinstance(candidate, torch.nn.Module):
            return candidate
    for candidate in vars(model).values():
        if isinstance(candidate, torch.nn.Module):
            return candidate
    return None


def _module_device(module: Any) -> str:
    try:
        return str(next(module.parameters()).device)
    except StopIteration:
        return "no-parameters"


def _resolve_snapshot(request: TimesFM25Request) -> Path:
    if request.snapshot_path is not None:
        snapshot = Path(request.snapshot_path)
        if not snapshot.exists():
            raise FileNotFoundError(f"snapshot_path does not exist: {snapshot}")
        return snapshot
    from huggingface_hub import snapshot_download

    return Path(
        snapshot_download(
            repo_id=request.repo_id,
            revision=request.revision,
            local_files_only=True,
            allow_patterns=["*.json", "*.safetensors", "README.md"],
        )
    )


def _run_native(request: TimesFM25Request) -> TimesFM25Response:
    if request.backend not in {Backend.PYTORCH_NATIVE, Backend.PYTORCH_SOURCE}:
        raise NotImplementedError(
            f"runtime backend is not implemented in this PR: {request.backend}"
        )

    import timesfm
    import torch

    if request.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CPU_FALLBACK_FORBIDDEN: CUDA was requested but is unavailable")
    np.random.seed(request.seed)
    torch.manual_seed(request.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(request.seed)
    registry = BackendRegistry(load_default_manifest())
    registry.validate_identity(request.backend, request.repo_id, request.revision)
    snapshot = _resolve_snapshot(request)
    requested_cuda = request.device == "cuda"
    if requested_cuda:
        torch.cuda.reset_peak_memory_stats()
        vram_before = torch.cuda.memory_allocated()
    else:
        vram_before = 0

    load_started = time.perf_counter()
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
        snapshot,
        local_files_only=True,
        torch_compile=request.forecast_config.torch_compile,
    )
    module = _find_torch_module(model, torch)
    if module is None:
        raise RuntimeError("MODEL_DEVICE_UNVERIFIED: no torch.nn.Module found in TimesFM wrapper")
    if requested_cuda:
        module.to("cuda")
    model_device = _module_device(module)
    load_seconds = time.perf_counter() - load_started

    compile_started = time.perf_counter()
    model.compile(timesfm.ForecastConfig(**build_native_forecast_config(request)))
    compile_seconds = time.perf_counter() - compile_started

    inputs = [
        np.asarray(request.history[series_id][-request.context_length :], dtype=np.float32)
        for series_id in request.series_ids
    ]
    inference_started = time.perf_counter()
    point_forecast, full_forecast = model.forecast(
        horizon=request.prediction_length,
        inputs=inputs,
    )
    if requested_cuda:
        torch.cuda.synchronize()
    inference_seconds = time.perf_counter() - inference_started
    median, mean, quantiles = split_native_outputs(point_forecast, full_forecast)

    weight_files = sorted(snapshot.rglob("*.safetensors"))
    config_path = snapshot / "config.json"
    external = query_nvidia_process(os.getpid()) if requested_cuda else query_nvidia_process(-1)
    vram_peak = torch.cuda.max_memory_allocated() if requested_cuda else 0
    vram_after = torch.cuda.memory_allocated() if requested_cuda else 0
    gpu_used = requested_cuda and model_device.startswith("cuda") and vram_peak > 0
    cpu_fallback = requested_cuda and not gpu_used
    # The native API returns NumPy arrays. Even when model execution is observed on CUDA,
    # the strict certification contract requires mean and quantile outputs to remain on CUDA.
    # Therefore the native lane is PARTIAL until an output-tensor evidence path exists.
    gpu_status = "PARTIAL"
    if cpu_fallback:
        gpu_status = "FAIL"

    backend_manifest = registry.resolve(request.backend)
    package_version = importlib.metadata.version("timesfm")
    response = TimesFM25Response(
        model_identity=ModelIdentity(
            backend=request.backend,
            checkpoint_repo_id=request.repo_id,
            checkpoint_revision=request.revision,
            package_version=package_version,
            source_revision=(
                registry.manifest.package_provenance.source_revision
                if request.backend == Backend.PYTORCH_SOURCE
                else None
            ),
            weight_sha256=backend_manifest.weight_sha256,
        ),
        effective_arguments=effective_argument_ledger(request),
        median_forecast=median.tolist(),
        mean_forecast=mean.tolist(),
        quantiles={key: value.tolist() for key, value in quantiles.items()},
        series_identity=request.series_ids,
        prediction_index=list(range(request.prediction_length)),
        runtime_evidence=RuntimeEvidence(
            provider_pid=os.getpid(),
            model_parameter_device=model_device,
            input_device="cpu_numpy_staging",
            mean_output_device="cpu_numpy",
            quantile_output_device="cpu_numpy",
            cpu_fallback=cpu_fallback,
            load_time_seconds=load_seconds,
            compile_time_seconds=compile_seconds,
            inference_time_seconds=inference_seconds,
            compile_requested=request.forecast_config.torch_compile,
            compile_effective=request.forecast_config.torch_compile,
            compile_backend="torch.compile" if request.forecast_config.torch_compile else None,
        ),
        gpu_evidence=GPUExecutionEvidence(
            requested=requested_cuda,
            cuda_available=torch.cuda.is_available(),
            gpu_used=gpu_used,
            provider_pid=os.getpid(),
            external_pid_match=external.external_pid_match,
            gpu_uuid=external.gpu_uuid,
            vram_before_bytes=vram_before,
            vram_peak_bytes=vram_peak,
            vram_after_bytes=vram_after,
            cpu_fallback=cpu_fallback,
            certification_status=("NOT_REQUESTED" if not requested_cuda else gpu_status),
            failure_reason=(
                "Native TimesFM returns CPU NumPy outputs, so strict CUDA output-device "
                "certification is not satisfied."
                if requested_cuda and gpu_used and external.external_pid_match
                else (
                    "GPU execution was not fully observed"
                    if requested_cuda and gpu_status != "PASS"
                    else None
                )
            ),
        ),
        artifact_reference=ArtifactReference(
            repo_id=request.repo_id,
            revision=request.revision,
            snapshot_path=str(snapshot),
            config_sha256=sha256_file(config_path) if config_path.exists() else None,
            weight_sha256={
                str(path.relative_to(snapshot)): sha256_file(path) for path in weight_files
            },
            snapshot_reloaded=(
                request.operation == "reload_predict" and request.snapshot_path is not None
            ),
        ),
        warnings=[
            "Native TimesFM accepts NumPy inputs and returns NumPy outputs; "
            "input/output CUDA tensor identity is therefore not asserted."
        ],
    )
    return response


def run(request: TimesFM25Request) -> TimesFM25Response:
    return _run_native(request)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TimesFM 2.5 provider contract v2")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = run(_load_request(args.request)).model_dump(mode="json")
    except Exception as exc:
        payload = {
            "status": "ERROR",
            "schema_version": 2,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    _write_payload(args.response, payload)


if __name__ == "__main__":
    main()

"""Isolated real-provider worker for AutoFreTS runtime certification."""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from .runtime_contracts import (
    AutoFreTSRuntimeRequest,
    AutoFreTSWorkerResponse,
    GPUProcessSampleRecord,
    load_runtime_request,
)
from .runtime_source import verify_working_source


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    content = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def synthetic_values(length: int, seed: int) -> list[float]:
    """Produce deterministic bounded values without reading project data."""

    return [float(((index * 11) + (seed * 5)) % 41 + 1) for index in range(length)]


def _prediction_matrix(
    frame: Any,
    *,
    alias: str,
    horizon: int,
) -> tuple[tuple[float, ...], ...]:
    if alias not in frame.columns:
        excluded = {"unique_id", "ds", "cutoff"}
        candidates = [column for column in frame.columns if column not in excluded]
        if len(candidates) != 1:
            raise RuntimeError(
                f"prediction output does not expose the expected alias: candidates={candidates}"
            )
        alias = candidates[0]
    values = [float(value) for value in frame[alias].tolist()]
    if len(values) != horizon:
        raise RuntimeError(f"prediction horizon mismatch: expected {horizon}, got {len(values)}")
    return (tuple(values),)


def _maximum_difference(
    first: tuple[tuple[float, ...], ...],
    second: tuple[tuple[float, ...], ...],
) -> float:
    if len(first) != len(second) or any(len(a) != len(b) for a, b in zip(first, second)):
        raise RuntimeError("pre-save and post-load prediction shapes differ")
    return max(abs(a - b) for row_a, row_b in zip(first, second) for a, b in zip(row_a, row_b))


def parse_nvidia_smi_output(
    text: str,
    provider_pid: int,
) -> tuple[GPUProcessSampleRecord, ...]:
    samples: list[GPUProcessSampleRecord] = []
    observed_at = datetime.now(UTC)
    for raw_line in text.splitlines():
        parts = [part.strip() for part in raw_line.strip().split(",")]
        if len(parts) != 3:
            continue
        pid_text, gpu_uuid, memory_mib_text = parts
        try:
            pid = int(pid_text)
            memory_mib = int(memory_mib_text)
        except ValueError:
            continue
        if pid != provider_pid or not gpu_uuid or memory_mib <= 0:
            continue
        samples.append(
            GPUProcessSampleRecord(
                provider_pid=pid,
                gpu_uuid=gpu_uuid,
                used_memory_bytes=memory_mib * 1024 * 1024,
                observed_at_utc=observed_at,
            )
        )
    return tuple(samples)


def _capture_gpu_samples(
    provider_pid: int,
) -> tuple[GPUProcessSampleRecord, ...]:
    command = [
        "nvidia-smi",
        "--query-compute-apps=pid,gpu_uuid,used_gpu_memory",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    if completed.returncode != 0:
        return ()
    return parse_nvidia_smi_output(completed.stdout, provider_pid)


def _walk_models(model: Any) -> list[Any]:
    visited: set[int] = set()
    queue = [model]
    result: list[Any] = []
    while queue:
        current = queue.pop(0)
        identity = id(current)
        if identity in visited:
            continue
        visited.add(identity)
        result.append(current)
        for attribute in ("model", "module", "best_model"):
            nested = getattr(current, attribute, None)
            if nested is not None:
                queue.append(nested)
        nested_models = getattr(current, "models", None)
        if isinstance(nested_models, (list, tuple)):
            queue.extend(nested_models)
    return result


def _parameter_device(model: Any) -> str:
    for current in _walk_models(model):
        parameters = getattr(current, "parameters", None)
        if not callable(parameters):
            continue
        try:
            parameter = next(parameters())
        except StopIteration:
            continue
        device_type = getattr(
            getattr(parameter, "device", None),
            "type",
            None,
        )
        if device_type in {"cpu", "cuda"}:
            return device_type
    raise RuntimeError("fitted model does not expose a CPU or CUDA parameter device")


def _fitted_model_class(model: Any) -> str:
    for current in _walk_models(model):
        if getattr(current, "loto_model_id", None) == "nf-local-auto-frets":
            return type(current).__name__
    return type(model).__name__


def _frets_evidence(model: Any) -> dict[str, Any]:
    candidate = None
    for current in _walk_models(model):
        if getattr(current, "loto_model_id", None) == "nf-local-auto-frets":
            candidate = current
            break
    if candidate is None:
        raise RuntimeError("reloaded model does not expose FreTS identity")

    architecture = getattr(candidate, "loto_architecture", None)
    if not isinstance(architecture, dict):
        raise RuntimeError("FreTS architecture evidence is missing")
    expected_parameter_count = int(architecture["expected_parameter_count"])
    temporal_fft_bins = int(architecture["temporal_fft_bins"])
    parameters = list(candidate.parameters())
    parameter_count = sum(parameter.numel() for parameter in parameters)
    if any(str(parameter.dtype) != "torch.float32" for parameter in parameters):
        raise RuntimeError("FreTS parameters are not all float32")
    if parameter_count != expected_parameter_count:
        raise RuntimeError(
            "FreTS runtime parameter count mismatch: "
            f"expected {expected_parameter_count}, got {parameter_count}"
        )
    fft_dtype = getattr(candidate, "loto_fft_dtype", None)
    channel_mixing = getattr(
        candidate,
        "loto_channel_frequency_mixing",
        None,
    )
    if fft_dtype != "float32":
        raise RuntimeError("FreTS runtime did not retain float32 FFT evidence")
    if channel_mixing is not False:
        raise RuntimeError("FreTS runtime unexpectedly enabled channel-frequency mixing")
    return {
        "fft_dtype": fft_dtype,
        "temporal_fft_bins": temporal_fft_bins,
        "channel_frequency_mixing": channel_mixing,
        "parameter_count": parameter_count,
        "expected_parameter_count": expected_parameter_count,
    }


def _fixed_model_config(
    request: AutoFreTSRuntimeRequest,
) -> dict[str, Any]:
    accelerator = "gpu" if request.requested_device == "cuda" else "cpu"
    return {
        "architecture_profile": request.architecture_profile.value,
        "training_profile": request.training_profile.value,
        "learning_rate": request.learning_rate,
        "batch_size": request.batch_size,
        "valid_batch_size": request.batch_size,
        "windows_batch_size": request.windows_batch_size,
        "inference_windows_batch_size": request.windows_batch_size,
        "scaler_type": request.scaler_type,
        "random_seed": request.seed,
        "accelerator": accelerator,
        "devices": 1,
        "precision": request.precision,
        "enable_checkpointing": False,
        "enable_progress_bar": False,
        "enable_model_summary": False,
        "logger": False,
        "deterministic": True,
        "benchmark": False,
        "num_sanity_val_steps": 0,
        "log_every_n_steps": 1,
    }


def _build_model(request: AutoFreTSRuntimeRequest, alias: str) -> Any:
    from neuralforecast.common._base_auto import OptunaOptions, RayOptions
    from optuna.samplers import RandomSampler
    from ray.tune.search.basic_variant import BasicVariantGenerator

    from .runtime import get_auto_frets_class, get_frets_class

    config = _fixed_model_config(request)
    if request.execution_mode == "direct":
        model_class = get_frets_class()
        return model_class(h=request.horizon, alias=alias, **config)

    auto_class = get_auto_frets_class()
    if request.execution_mode == "ray":
        return auto_class(
            h=request.horizon,
            alias=alias,
            backend="ray",
            config=config,
            search_alg=BasicVariantGenerator(random_state=request.seed),
            num_samples=1,
            ray_options=RayOptions(
                cpus=1,
                gpus=1 if request.requested_device == "cuda" else 0,
            ),
        )

    def optuna_config(_trial: Any) -> dict[str, Any]:
        return dict(config)

    return auto_class(
        h=request.horizon,
        alias=alias,
        backend="optuna",
        config=optuna_config,
        search_alg=RandomSampler(seed=request.seed),
        num_samples=1,
        optuna_options=OptunaOptions(study_kwargs={"n_jobs": 1}),
    )


def _run_provider(
    request: AutoFreTSRuntimeRequest,
    *,
    run_label: str,
    output_root: Path,
) -> AutoFreTSWorkerResponse:
    working_directory = Path(request.working_directory)
    verify_working_source(
        working_directory,
        expected_revision=request.source_revision,
        expected_tree_sha256=request.source_tree_sha256,
    )

    import numpy as np
    import pandas as pd
    import torch
    from neuralforecast import NeuralForecast

    installed_version = metadata.version("neuralforecast")
    if installed_version != request.expected_neuralforecast_version:
        raise RuntimeError(
            "neuralforecast version mismatch: "
            f"expected {request.expected_neuralforecast_version}, "
            f"got {installed_version}"
        )
    if request.requested_device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")

    random.seed(request.seed)
    np.random.seed(request.seed)
    torch.manual_seed(request.seed)
    if request.requested_device == "cuda":
        torch.cuda.manual_seed_all(request.seed)
        torch.cuda.reset_peak_memory_stats()

    values = synthetic_values(request.history_length, request.seed)
    history = pd.DataFrame(
        {
            "unique_id": ["runtime-series"] * request.history_length,
            "ds": list(range(1, request.history_length + 1)),
            "y": np.asarray(values, dtype=np.float32),
        }
    )
    if history.isna().any().any() or not np.isfinite(history["y"].to_numpy()).all():
        raise RuntimeError("synthetic runtime input is invalid")
    if history["y"].to_numpy().dtype != np.float32:
        raise RuntimeError("synthetic FreTS input must be float32")

    alias = f"AutoFreTS-{request.execution_mode}"
    model = _build_model(request, alias)
    forecast = NeuralForecast(models=[model], freq=1)
    forecast.fit(df=history, val_size=request.validation_size)
    pre_reload = _prediction_matrix(
        forecast.predict(),
        alias=alias,
        horizon=request.horizon,
    )

    bundle_path = output_root / "model_bundle"
    forecast.save(
        path=str(bundle_path),
        overwrite=True,
        save_dataset=True,
    )
    reloaded = NeuralForecast.load(
        path=str(bundle_path),
        map_location=request.requested_device,
    )
    post_reload = _prediction_matrix(
        reloaded.predict(),
        alias=alias,
        horizon=request.horizon,
    )
    maximum_difference = _maximum_difference(
        pre_reload,
        post_reload,
    )
    if maximum_difference > request.replay_tolerance:
        raise RuntimeError(
            "save/reload replay exceeded tolerance: "
            f"difference={maximum_difference}, "
            f"tolerance={request.replay_tolerance}"
        )

    fitted_model = reloaded.models[0]
    model_evidence = _frets_evidence(fitted_model)
    effective_device = _parameter_device(fitted_model)
    cpu_fallback = request.requested_device == "cuda" and effective_device != "cuda"
    provider_pid = os.getpid()
    if effective_device == "cuda":
        peak_vram = max(
            int(torch.cuda.max_memory_allocated()),
            int(torch.cuda.max_memory_reserved()),
        )
        samples = _capture_gpu_samples(provider_pid)
        if not samples:
            raise RuntimeError("CUDA execution lacks matching nvidia-smi PID evidence")
        gpu_uuid = samples[0].gpu_uuid
        provider_gpu_pid = provider_pid
    else:
        peak_vram = 0
        samples = ()
        gpu_uuid = None
        provider_gpu_pid = None

    return AutoFreTSWorkerResponse(
        status="PASS",
        run_label=run_label,
        execution_mode=request.execution_mode,
        provider_pid=provider_pid,
        package_version=installed_version,
        source_revision=request.source_revision,
        source_tree_sha256=request.source_tree_sha256,
        requested_device=request.requested_device,
        effective_device=effective_device,
        cpu_fallback=cpu_fallback,
        provider_gpu_pid=provider_gpu_pid,
        gpu_uuid=gpu_uuid,
        peak_vram_bytes=peak_vram,
        external_gpu_samples=samples,
        output=post_reload,
        pre_reload_output=pre_reload,
        source_verified=True,
        package_verified=True,
        load_success=True,
        input_validation_success=True,
        fit_success=True,
        inference_success=True,
        save_succeeded=True,
        reload_succeeded=True,
        re_predict_succeeded=True,
        auto_backend_executed=request.execution_mode != "direct",
        maximum_reload_difference=maximum_difference,
        bundle_path=str(bundle_path.resolve()),
        fitted_model_class=_fitted_model_class(fitted_model),
        **model_evidence,
    )


def run_worker(
    request_path: Path,
    output_path: Path,
    run_label: str,
) -> int:
    provider_pid = os.getpid()
    try:
        request = load_runtime_request(request_path)
        response = _run_provider(
            request,
            run_label=run_label,
            output_root=output_path.parent,
        )
    except Exception as exc:
        try:
            request = load_runtime_request(request_path)
            requested_device = request.requested_device
            execution_mode = request.execution_mode
        except Exception:
            requested_device = "cpu"
            execution_mode = "direct"
        response = AutoFreTSWorkerResponse(
            status="FAILED",
            run_label=run_label,
            execution_mode=execution_mode,
            provider_pid=provider_pid,
            requested_device=requested_device,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        _atomic_write_json(
            output_path,
            response.model_dump(mode="json"),
        )
        return 2
    _atomic_write_json(
        output_path,
        response.model_dump(mode="json"),
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--run-label",
        choices=("run-a", "run-b"),
        required=True,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_worker(args.request, args.output, args.run_label)


if __name__ == "__main__":
    sys.exit(main())

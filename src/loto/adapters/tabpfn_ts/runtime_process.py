from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from .hash_gate import formal_runtime_environment
from .manifests import CheckpointLane, require_executable_lane
from .runtime_gpu import parameter_devices, query_nvidia_compute_apps, validate_provider_response
from .runtime_models import (
    GPUProcessSample,
    ProviderRunEvidence,
    RuntimeCertificationConfig,
    RuntimeCertificationError,
    canonical_prediction_sha256,
    load_json,
    sha256_path,
    utc_now,
    write_json_atomic,
)

GPUProbe = Callable[[str], list[GPUProcessSample]]


def build_formal_provider_request(
    source: Mapping[str, Any],
    *,
    snapshot_path: Path,
    device: Literal["cpu", "cuda"],
    seed: int,
) -> dict[str, Any]:
    manifest = require_executable_lane(CheckpointLane.V2_REG_LEGACY)
    payload = dict(source)
    if not isinstance(payload.get("history"), list) or not payload["history"]:
        raise RuntimeCertificationError("provider request requires non-empty history")
    if int(payload.get("prediction_length", 1)) != 1:
        raise RuntimeCertificationError(
            "legacy V2 runtime certification requires prediction_length=1"
        )
    payload.update(
        {
            "schema_version": 1,
            "repo_id": manifest.repo_id,
            "revision": manifest.revision,
            "weight_filename": manifest.filename,
            "snapshot_path": str(snapshot_path.absolute()),
            "prediction_length": 1,
            "device": device,
            "seed": seed,
            "local_files_only": True,
            "offline_required": True,
            "telemetry_disabled": True,
            "network_access": False,
            "license_accepted": True,
        }
    )
    return payload


def compare_process_replays(
    process_runs: Sequence[ProviderRunEvidence],
    *,
    absolute_tolerance: float,
) -> tuple[bool, float]:
    if len(process_runs) < 2:
        raise RuntimeCertificationError("at least two process runs are required")
    if len({run.process_pid for run in process_runs}) != len(process_runs):
        raise RuntimeCertificationError("replay must use distinct provider processes")
    reference = process_runs[0].predictions
    maximum = 0.0
    for run in process_runs[1:]:
        if len(run.predictions) != len(reference):
            raise RuntimeCertificationError("replay prediction lengths differ")
        for left, right in zip(reference, run.predictions, strict=True):
            maximum = max(maximum, abs(left - right))
    return maximum <= absolute_tolerance, maximum


def _deduplicate_samples(samples: Sequence[GPUProcessSample]) -> list[GPUProcessSample]:
    seen: set[tuple[int, str, int]] = set()
    result: list[GPUProcessSample] = []
    for sample in samples:
        key = (sample.pid, sample.gpu_uuid, sample.used_memory_bytes)
        if key not in seen:
            seen.add(key)
            result.append(sample)
    return result


def run_provider_process(
    config: RuntimeCertificationConfig,
    *,
    run_index: int,
    formal_request: Mapping[str, Any],
    gpu_probe: GPUProbe = query_nvidia_compute_apps,
) -> ProviderRunEvidence:
    run_dir = config.output_root / config.run_id / f"process-{run_index:02d}"
    run_dir.mkdir(parents=True, exist_ok=False)
    request_path = run_dir / "request.json"
    response_path = run_dir / "response.json"
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    write_json_atomic(request_path, formal_request)

    environment = formal_runtime_environment()
    environment["PYTHONHASHSEED"] = str(config.seed)
    environment["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    source_path = str((config.repo_root / "src").resolve())
    current_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = (
        source_path if not current_pythonpath else source_path + os.pathsep + current_pythonpath
    )
    command = [
        str(config.provider_python),
        str(config.provider_script),
        "--request",
        str(request_path),
        "--response",
        str(response_path),
        "--certification-hold-seconds",
        str(config.hold_seconds),
    ]

    started_at = utc_now()
    samples: list[GPUProcessSample] = []
    with stdout_path.open("w", encoding="utf-8") as stdout_stream, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_stream:
        process = subprocess.Popen(
            command,
            cwd=config.repo_root,
            env=environment,
            stdout=stdout_stream,
            stderr=stderr_stream,
            text=True,
        )
        deadline = time.monotonic() + config.process_timeout_seconds
        while process.poll() is None:
            if time.monotonic() >= deadline:
                process.kill()
                process.wait(timeout=10)
                raise RuntimeCertificationError(
                    f"provider process timed out after {config.process_timeout_seconds}s"
                )
            if config.device == "cuda":
                try:
                    samples.extend(
                        sample
                        for sample in gpu_probe(config.nvidia_smi_command)
                        if sample.pid == process.pid
                    )
                except RuntimeCertificationError:
                    if response_path.exists():
                        raise
            time.sleep(config.poll_interval_seconds)
        exit_code = int(process.returncode)

    finished_at = utc_now()
    if not response_path.is_file():
        raise RuntimeCertificationError(
            f"provider response was not created; exit={exit_code}, stderr={stderr_path}"
        )
    response = load_json(response_path)
    if exit_code != 0:
        raise RuntimeCertificationError(
            f"provider process returned non-zero exit code: {exit_code}"
        )
    external_samples = _deduplicate_samples(samples)
    predictions, gpu_evidence = validate_provider_response(
        response,
        expected_device=config.device,
        process_pid=process.pid,
        external_samples=external_samples,
        expected_seed=config.seed,
    )
    remaining_pids = (
        {sample.pid for sample in gpu_probe(config.nvidia_smi_command)}
        if config.device == "cuda"
        else set()
    )
    if process.pid in remaining_pids:
        raise RuntimeCertificationError("provider GPU PID remained active after process exit")

    return ProviderRunEvidence(
        run_index=run_index,
        process_pid=process.pid,
        exit_code=exit_code,
        started_at_utc=started_at,
        finished_at_utc=finished_at,
        request_path=str(request_path),
        response_path=str(response_path),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        response_sha256=sha256_path(response_path),
        prediction_sha256=canonical_prediction_sha256(predictions),
        predictions=predictions,
        prediction_shape=[37],
        requested_device=config.device,
        execution_device=str(gpu_evidence["execution_device"]),
        cpu_fallback=bool(gpu_evidence["cpu_fallback"]),
        provider_gpu_pid=(
            int(gpu_evidence["gpu_pid"]) if gpu_evidence.get("gpu_pid") is not None else None
        ),
        provider_peak_vram_bytes=int(gpu_evidence.get("peak_vram_bytes", 0)),
        parameter_devices=parameter_devices(response),
        external_gpu_samples=external_samples,
        pid_released_after_exit=True,
    )

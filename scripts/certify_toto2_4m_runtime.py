from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.adapters.toto2_4m import (  # noqa: E402
    RuntimeEvidence,
    Toto2ProviderRequest,
    Toto2ProviderResponse,
    Toto2ResponseAdapter,
)
from loto.toto2_campaign.gpu_evidence import (  # noqa: E402
    GpuProcessSample,
    parse_compute_apps_csv,
    summarize_pid_samples,
)
from loto.toto2_campaign.replay import compare_native_outputs  # noqa: E402


@dataclass(frozen=True)
class ProcessResult:
    run_dir: Path
    native_output_path: Path
    runtime_evidence: RuntimeEvidence
    artifact_reference: dict[str, Any]
    gpu_summary: dict[str, object]


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _query_compute_apps() -> list[GpuProcessSample]:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,gpu_uuid,used_memory",
            "--format=csv,noheader,nounits",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "nvidia-smi compute-app query failed: "
            f"returncode={completed.returncode} stderr={completed.stderr.strip()}"
        )
    return parse_compute_apps_csv(completed.stdout)


def _wait_for_ready(
    process: subprocess.Popen[str],
    ready_path: Path,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while not ready_path.exists():
        returncode = process.poll()
        if returncode is not None:
            raise RuntimeError(f"isolated provider exited before ready: {returncode}")
        if time.monotonic() >= deadline:
            process.terminate()
            raise RuntimeError(f"isolated provider ready timeout: {timeout_seconds:.1f}s")
        time.sleep(0.05)
    return _load_json(ready_path)


def _sample_until_pid(
    process: subprocess.Popen[str],
    provider_pid: int,
    *,
    timeout_seconds: float,
) -> list[GpuProcessSample]:
    captured: list[GpuProcessSample] = []
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        captured.extend(sample for sample in _query_compute_apps() if sample.pid == provider_pid)
        if captured:
            return captured
        time.sleep(0.05)
    return captured


def _drain_process_gpu_samples(
    process: subprocess.Popen[str],
    provider_pid: int,
    captured: list[GpuProcessSample],
) -> None:
    while process.poll() is None:
        captured.extend(sample for sample in _query_compute_apps() if sample.pid == provider_pid)
        time.sleep(0.05)


def _augment_runtime_evidence(
    evidence: RuntimeEvidence,
    gpu_summary: dict[str, object],
) -> RuntimeEvidence:
    payload = evidence.model_dump(mode="json")
    captured = bool(gpu_summary["captured"])
    max_mib = int(gpu_summary["max_gpu_memory_mib"])
    payload.update(
        {
            "external_gpu_pid_captured": captured,
            "peak_vram_bytes": max(int(evidence.peak_vram_bytes), max_mib * 1024 * 1024),
        }
    )
    return RuntimeEvidence.model_validate(payload)


def _run_one_process(
    request: Toto2ProviderRequest,
    *,
    request_path: Path,
    snapshot_path: Path,
    isolated_python: Path,
    process_root: Path,
    ready_timeout_seconds: float,
    gpu_capture_timeout_seconds: float,
) -> ProcessResult:
    ready_path = process_root.with_name(f"{process_root.name}.ready.json")
    start_path = process_root.with_name(f"{process_root.name}.start")
    stdout_path = process_root.with_name(f"{process_root.name}.stdout.log")
    stderr_path = process_root.with_name(f"{process_root.name}.stderr.log")
    command = [
        str(isolated_python),
        str(ROOT / "scripts" / "run_toto2_4m_isolated.py"),
        "--request",
        str(request_path),
        "--snapshot",
        str(snapshot_path),
        "--run-dir",
        str(process_root),
        "--ready",
        str(ready_path),
        "--start",
        str(start_path),
        "--handshake-timeout-seconds",
        str(ready_timeout_seconds),
    ]
    with (
        stdout_path.open("w", encoding="utf-8") as stdout_handle,
        stderr_path.open("w", encoding="utf-8") as stderr_handle,
    ):
        process = subprocess.Popen(
            command,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
        )
        ready = _wait_for_ready(process, ready_path, timeout_seconds=ready_timeout_seconds)
        provider_pid = int(ready["provider_pid"])
        if provider_pid != process.pid:
            process.terminate()
            raise RuntimeError(
                f"provider PID mismatch: ready={provider_pid}, process={process.pid}"
            )

        captured: list[GpuProcessSample] = []
        if request.device == "cuda":
            captured = _sample_until_pid(
                process,
                provider_pid,
                timeout_seconds=gpu_capture_timeout_seconds,
            )
            if not captured:
                process.terminate()
                raise RuntimeError("external GPU PID capture failed before inference")
        start_path.write_text("START\n", encoding="utf-8")
        if request.device == "cuda":
            _drain_process_gpu_samples(process, provider_pid, captured)
        returncode = process.wait(timeout=ready_timeout_seconds)

    if returncode != 0:
        result_path = process_root / "executor_result.json"
        detail = _load_json(result_path) if result_path.exists() else {}
        raise RuntimeError(f"isolated provider failed: returncode={returncode} detail={detail}")

    native_output_path = process_root / "native_output.npy"
    evidence = RuntimeEvidence.model_validate(
        _load_json(process_root / "runtime_evidence.internal.json")
    )
    artifact_reference = _load_json(process_root / "artifact_reference.json")
    gpu_summary = summarize_pid_samples(captured, provider_pid)
    if request.device == "cuda" and not bool(gpu_summary["captured"]):
        raise RuntimeError("CUDA inference completed without external GPU PID evidence")
    evidence = _augment_runtime_evidence(evidence, gpu_summary)
    _atomic_write_json(
        process_root / "runtime_evidence.json",
        evidence.model_dump(mode="json"),
    )
    _atomic_write_json(process_root / "external_gpu_pid_evidence.json", gpu_summary)
    return ProcessResult(
        run_dir=process_root,
        native_output_path=native_output_path,
        runtime_evidence=evidence,
        artifact_reference=artifact_reference,
        gpu_summary=gpu_summary,
    )


def certify(
    request_path: Path,
    *,
    response_path: Path,
    snapshot_path: Path,
    isolated_python: Path,
    run_dir: Path,
    ready_timeout_seconds: float,
    gpu_capture_timeout_seconds: float,
) -> Toto2ProviderResponse:
    request = Toto2ProviderRequest.model_validate(_load_json(request_path))
    if request.operation.value != "predict":
        raise ValueError("runtime certification accepts only predict requests")
    if run_dir.exists():
        raise FileExistsError(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)

    first = _run_one_process(
        request,
        request_path=request_path,
        snapshot_path=snapshot_path,
        isolated_python=isolated_python,
        process_root=run_dir / "process-1",
        ready_timeout_seconds=ready_timeout_seconds,
        gpu_capture_timeout_seconds=gpu_capture_timeout_seconds,
    )
    second = _run_one_process(
        request,
        request_path=request_path,
        snapshot_path=snapshot_path,
        isolated_python=isolated_python,
        process_root=run_dir / "process-2",
        ready_timeout_seconds=ready_timeout_seconds,
        gpu_capture_timeout_seconds=gpu_capture_timeout_seconds,
    )
    replay = compare_native_outputs(first.native_output_path, second.native_output_path)
    _atomic_write_json(run_dir / "REPLAY_COMPARISON.json", replay)
    if not bool(replay["exact_equal"]):
        raise RuntimeError(f"two-process native output mismatch: {replay}")

    native_output = np.load(first.native_output_path, allow_pickle=False)
    artifact_reference = dict(first.artifact_reference)
    artifact_reference["replay"] = replay
    artifact_reference["processes"] = [
        {
            "run_dir": str(first.run_dir),
            "runtime_evidence": first.runtime_evidence.model_dump(mode="json"),
            "gpu_evidence": first.gpu_summary,
        },
        {
            "run_dir": str(second.run_dir),
            "runtime_evidence": second.runtime_evidence.model_dump(mode="json"),
            "gpu_evidence": second.gpu_summary,
        },
    ]
    response = Toto2ResponseAdapter.from_native(
        request,
        native_output,
        runtime_evidence=first.runtime_evidence,
        artifact_reference=artifact_reference,
    )
    _atomic_write_json(response_path, response.model_dump(mode="json"))
    _atomic_write_json(
        run_dir / "CERTIFICATION_RESULT.json",
        {
            "status": "PASS",
            "response_path": str(response_path),
            "two_process_exact_replay": True,
            "runtime_scope": "FULL_INFERENCE",
            "forecast_accuracy_certified": False,
            "lottery_domain_compatibility_certified": False,
        },
    )
    return response


def main() -> int:
    parser = argparse.ArgumentParser(description="Certify Toto 2.0 4M isolated runtime")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--isolated-python", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--ready-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--gpu-capture-timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()

    try:
        response = certify(
            args.request,
            response_path=args.response,
            snapshot_path=args.snapshot,
            isolated_python=args.isolated_python,
            run_dir=args.run_dir,
            ready_timeout_seconds=args.ready_timeout_seconds,
            gpu_capture_timeout_seconds=args.gpu_capture_timeout_seconds,
        )
        return 0 if response.status == "OK" else 2
    except (OSError, RuntimeError, ValueError, ValidationError) as exc:
        _atomic_write_json(
            args.response,
            Toto2ProviderResponse(
                status="ERROR",
                phase="runtime_certification",
                message=f"{type(exc).__name__}: {exc}",
            ).model_dump(mode="json"),
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

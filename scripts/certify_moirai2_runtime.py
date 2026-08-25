from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.adapters.moirai2.contracts import (  # noqa: E402
    Moirai2ProviderRequest,
    Moirai2ProviderResponse,
)
from loto.moirai2_campaign.runtime_certification import (  # noqa: E402
    ComputeProcessRecord,
    GpuMemoryRecord,
    RuntimeCertificationError,
    certify_external_gpu_evidence,
    compare_provider_responses,
    parse_compute_process_csv,
    parse_gpu_memory_csv,
    sha256_file,
    sha256_payload,
    write_sha256_manifest,
)
from loto.moirai2_campaign.runtime_preflight import (  # noqa: E402
    RuntimePreflightError,
    run_frozen_probe,
    validate_lane_files,
)

RUNNER = ROOT / "scripts" / "run_moirai2_provider.py"
RUNTIME_LANES = {
    "supported-py311": ROOT / "environments" / "moirai2-supported-py311",
    "cuda13-experimental": ROOT / "environments" / "moirai2-cuda13-experimental",
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _query_nvidia_smi(arguments: list[str]) -> tuple[str, str | None]:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return "", "nvidia-smi is not installed"
    process = subprocess.run(
        [executable, *arguments],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if process.returncode != 0:
        return "", process.stderr.strip() or process.stdout.strip() or "nvidia-smi failed"
    return process.stdout, None


def _capture_gpu_state() -> dict[str, Any]:
    memory_text, memory_error = _query_nvidia_smi(
        ["--query-gpu=uuid,memory.used", "--format=csv,noheader,nounits"]
    )
    process_text, process_error = _query_nvidia_smi(
        [
            "--query-compute-apps=pid,gpu_uuid,used_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    memory: list[GpuMemoryRecord] = []
    processes: list[ComputeProcessRecord] = []
    errors = [error for error in (memory_error, process_error) if error]
    if memory_text:
        memory = parse_gpu_memory_csv(memory_text)
    if process_text:
        processes = parse_compute_process_csv(process_text)
    return {
        "captured_at_unix_ns": time.time_ns(),
        "memory": [record.__dict__ for record in memory],
        "processes": [record.__dict__ for record in processes],
        "errors": errors,
    }


def _records(snapshot: dict[str, Any]) -> tuple[list[GpuMemoryRecord], list[ComputeProcessRecord]]:
    memory = [GpuMemoryRecord(**record) for record in snapshot["memory"]]
    processes = [ComputeProcessRecord(**record) for record in snapshot["processes"]]
    return memory, processes


def _parse_python_version(raw: str) -> tuple[int, int, int]:
    token = raw.strip().split(maxsplit=1)[0]
    parts = token.split(".")
    if len(parts) < 2 or len(parts) > 3 or any(not part.isdigit() for part in parts):
        raise RuntimeCertificationError(f"invalid Python version from frozen probe: {raw!r}")
    values = [int(part) for part in parts]
    while len(values) < 3:
        values.append(0)
    return values[0], values[1], values[2]


def _parse_version_literal(raw: str) -> tuple[int, int, int]:
    parts = raw.strip().split(".")
    if not 1 <= len(parts) <= 3 or any(not part.isdigit() for part in parts):
        raise RuntimeCertificationError(f"unsupported requires-python version: {raw!r}")
    values = [int(part) for part in parts]
    while len(values) < 3:
        values.append(0)
    return values[0], values[1], values[2]


def _python_matches_requires(version: tuple[int, int, int], specifier: str) -> bool:
    clauses = [clause.strip() for clause in specifier.split(",") if clause.strip()]
    if not clauses:
        raise RuntimeCertificationError("runtime lane requires-python is empty")
    operators = (">=", "<=", "==", ">", "<")
    for clause in clauses:
        operator = next((candidate for candidate in operators if clause.startswith(candidate)), None)
        if operator is None:
            raise RuntimeCertificationError(
                f"unsupported requires-python clause for fail-closed validation: {clause!r}"
            )
        expected = _parse_version_literal(clause[len(operator) :])
        comparisons = {
            ">=": version >= expected,
            "<=": version <= expected,
            "==": version == expected,
            ">": version > expected,
            "<": version < expected,
        }
        if not comparisons[operator]:
            return False
    return True


def _prepare_lane_interpreter(
    *,
    request: Moirai2ProviderRequest,
    runtime_lane: str,
    timeout_seconds: int,
) -> tuple[Path, dict[str, Any]]:
    """Bind direct provider execution to the exact frozen/reviewed lane.

    The certifier needs the provider PID itself, so the provider is launched through
    the lane interpreter rather than a nested ``uv run`` process.  The direct
    interpreter is trusted only after the same frozen lane checks used by the formal
    campaign prove that the lock, snapshot, imports, Python version, and requested
    device all match the selected lane.
    """

    environment_path = RUNTIME_LANES[runtime_lane]
    if request.snapshot_path is None:
        raise RuntimeCertificationError("runtime preflight requires snapshot_path")
    snapshot_path = Path(request.snapshot_path)
    try:
        lane_files = validate_lane_files(
            environment_path,
            snapshot_path,
            runtime_lane=runtime_lane,
        )
        probe = run_frozen_probe(
            environment_path=environment_path,
            requested_device=request.device,
            timeout_seconds=min(timeout_seconds, 300),
        )
    except RuntimePreflightError as exc:
        raise RuntimeCertificationError(f"frozen runtime lane preflight failed: {exc}") from exc

    pyproject_payload = tomllib.loads(
        (environment_path / "pyproject.toml").read_text(encoding="utf-8")
    )
    project = pyproject_payload.get("project")
    requires_python = project.get("requires-python") if isinstance(project, dict) else None
    if not isinstance(requires_python, str) or not requires_python.strip():
        raise RuntimeCertificationError("runtime lane requires-python is missing")
    python_version_raw = probe.get("python_version")
    if not isinstance(python_version_raw, str):
        raise RuntimeCertificationError("frozen probe did not report python_version")
    python_version = _parse_python_version(python_version_raw)
    if not _python_matches_requires(python_version, requires_python):
        raise RuntimeCertificationError(
            "frozen probe Python does not satisfy runtime lane requires-python: "
            f"version={python_version_raw!r}, requires={requires_python!r}"
        )

    lane_python = environment_path / ".venv" / "bin" / "python"
    if not lane_python.is_file():
        raise RuntimeCertificationError(
            f"frozen runtime probe passed but lane interpreter is missing: {lane_python}"
        )
    probe_executable_raw = probe.get("python_executable")
    if not isinstance(probe_executable_raw, str) or not probe_executable_raw:
        raise RuntimeCertificationError("frozen probe did not report python_executable")
    probe_executable = Path(probe_executable_raw)
    expected_parent = lane_python.absolute().parent
    actual_parent = probe_executable.absolute().parent
    if actual_parent != expected_parent or probe_executable.resolve() != lane_python.resolve():
        raise RuntimeCertificationError(
            "frozen probe interpreter does not match selected lane interpreter: "
            f"probe={probe_executable}, expected={lane_python}"
        )

    evidence = {
        "runtime_lane": runtime_lane,
        "environment_path": str(environment_path.resolve()),
        "lane_python": str(lane_python.absolute()),
        "requires_python": requires_python,
        "python_version": python_version_raw,
        "python_executable": probe_executable_raw,
        "requested_device": request.device,
        "lane_files": lane_files,
        "frozen_probe": probe,
    }
    return lane_python, evidence


def _run_once(
    *,
    label: str,
    request: Moirai2ProviderRequest,
    runtime_lane: str,
    lane_python: Path,
    output_dir: Path,
    timeout_seconds: int,
    monitor_interval_seconds: float,
) -> dict[str, Any]:
    run_dir = output_dir / label
    run_dir.mkdir(parents=False, exist_ok=False)
    request_path = run_dir / "request.json"
    response_path = run_dir / "response.json"
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")

    # The interpreter was already bound to the frozen lane by
    # _prepare_lane_interpreter().  Never fall back to an arbitrary existing venv.
    command = [
        str(lane_python),
        str(RUNNER),
        "--request",
        str(request_path),
        "--response",
        str(response_path),
        "--runtime-lane",
        runtime_lane,
    ]
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    if request.device == "cpu":
        environment["CUDA_VISIBLE_DEVICES"] = ""

    before = _capture_gpu_state()
    samples: list[dict[str, Any]] = []
    started_ns = time.time_ns()
    with (
        stdout_path.open("w", encoding="utf-8") as stdout_stream,
        stderr_path.open("w", encoding="utf-8") as stderr_stream,
    ):
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=environment,
            stdout=stdout_stream,
            stderr=stderr_stream,
            text=True,
        )
        deadline = time.monotonic() + timeout_seconds
        while True:
            samples.append(_capture_gpu_state())
            return_code = process.poll()
            if return_code is not None:
                break
            if time.monotonic() >= deadline:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                raise RuntimeCertificationError(
                    f"provider {label} exceeded timeout={timeout_seconds}s"
                )
            time.sleep(monitor_interval_seconds)
    ended_ns = time.time_ns()
    after = _capture_gpu_state()
    (run_dir / "exit_code.txt").write_text(f"{return_code}\n", encoding="utf-8")
    _write_json(
        run_dir / "gpu_monitor.json",
        {
            "before": before,
            "samples": samples,
            "after": after,
        },
    )
    if return_code != 0:
        raise RuntimeCertificationError(
            f"provider {label} failed with exit code {return_code}; see {stderr_path}"
        )
    if not response_path.is_file():
        raise RuntimeCertificationError(f"provider {label} did not write response.json")
    response = Moirai2ProviderResponse.model_validate_json(
        response_path.read_text(encoding="utf-8")
    ).model_dump(mode="json")
    response_pid = int(response["runtime_evidence"]["process_id"])
    if response_pid != process.pid:
        raise RuntimeCertificationError(
            f"provider PID mismatch: popen={process.pid}, response={response_pid}"
        )

    before_memory, _ = _records(before)
    after_memory, after_processes = _records(after)
    process_samples = [
        ComputeProcessRecord(**record) for sample in samples for record in sample["processes"]
    ]
    external_gpu = certify_external_gpu_evidence(
        response=response,
        samples=process_samples,
        before_memory=before_memory,
        after_memory=after_memory,
        after_processes=after_processes,
    )
    evidence = {
        "label": label,
        "command": command,
        "process_id": process.pid,
        "started_at_unix_ns": started_ns,
        "ended_at_unix_ns": ended_ns,
        "duration_seconds": (ended_ns - started_ns) / 1_000_000_000,
        "request_sha256": sha256_file(request_path),
        "response_sha256": sha256_file(response_path),
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_sha256": sha256_file(stderr_path),
        "external_gpu": external_gpu.as_dict(),
        "response": response,
    }
    _write_json(run_dir / "run_evidence.json", evidence)
    return evidence


def _validate_inputs(
    request: Moirai2ProviderRequest,
    runtime_lane: str,
    monitor_interval_seconds: float,
) -> None:
    if request.operation.value != "predict":
        raise RuntimeCertificationError("P8 certification accepts only predict requests")
    if request.snapshot_path is None:
        raise RuntimeCertificationError(
            "P8 certification requires an explicit pinned local snapshot_path"
        )
    if runtime_lane not in RUNTIME_LANES:
        raise RuntimeCertificationError(f"unsupported runtime lane: {runtime_lane}")
    if request.device == "cuda" and runtime_lane != "cuda13-experimental":
        raise RuntimeCertificationError("CUDA certification requires cuda13-experimental lane")
    if monitor_interval_seconds <= 0 or monitor_interval_seconds > 5:
        raise RuntimeCertificationError("monitor interval must be in the range (0, 5]")
    if not RUNNER.is_file():
        raise RuntimeCertificationError(f"provider runner is missing: {RUNNER}")
    if not (RUNTIME_LANES[runtime_lane] / "pyproject.toml").is_file():
        raise RuntimeCertificationError("runtime lane pyproject.toml is missing")


def certify(
    *,
    request_path: Path,
    runtime_lane: str,
    output_dir: Path,
    timeout_seconds: int,
    monitor_interval_seconds: float,
) -> dict[str, Any]:
    request = Moirai2ProviderRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    _validate_inputs(request, runtime_lane, monitor_interval_seconds)
    output_dir.mkdir(parents=True, exist_ok=False)
    request_payload = request.model_dump(mode="json")
    _write_json(output_dir / "certification_request.json", request_payload)

    lane_python, runtime_preflight = _prepare_lane_interpreter(
        request=request,
        runtime_lane=runtime_lane,
        timeout_seconds=timeout_seconds,
    )
    _write_json(output_dir / "runtime_preflight.json", runtime_preflight)

    first = _run_once(
        label="run-a",
        request=request,
        runtime_lane=runtime_lane,
        lane_python=lane_python,
        output_dir=output_dir,
        timeout_seconds=timeout_seconds,
        monitor_interval_seconds=monitor_interval_seconds,
    )
    second = _run_once(
        label="run-b",
        request=request,
        runtime_lane=runtime_lane,
        lane_python=lane_python,
        output_dir=output_dir,
        timeout_seconds=timeout_seconds,
        monitor_interval_seconds=monitor_interval_seconds,
    )
    comparison = compare_provider_responses(first["response"], second["response"])
    result = {
        "status": "PASS",
        "phase": "P8_RUNTIME_CERTIFICATION",
        "run_id": request.run_id,
        "runtime_lane": runtime_lane,
        "requested_device": request.device,
        "request_sha256": sha256_payload(request_payload),
        "runtime_preflight_sha256": sha256_file(output_dir / "runtime_preflight.json"),
        "lane_python": str(lane_python.absolute()),
        "separate_process_reload": True,
        "save_load_status": "BASE_SNAPSHOT_RELOADED",
        "prediction_comparison": comparison.as_dict(),
        "run_a": {key: value for key, value in first.items() if key != "response"},
        "run_b": {key: value for key, value in second.items() if key != "response"},
    }
    _write_json(output_dir / "certification.json", result)
    write_sha256_manifest(output_dir, output_dir / "SHA256SUMS")
    _write_json(
        output_dir / "ARTIFACT_MANIFEST.json",
        {
            "status": "PASS",
            "files": sorted(
                path.relative_to(output_dir).as_posix()
                for path in output_dir.rglob("*")
                if path.is_file()
            ),
        },
    )
    write_sha256_manifest(output_dir, output_dir / "SHA256SUMS")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Certify Moirai 2.0 in two isolated provider processes"
    )
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--runtime-lane", required=True, choices=sorted(RUNTIME_LANES))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--monitor-interval-seconds", type=float, default=0.25)
    arguments = parser.parse_args()
    try:
        certify(
            request_path=arguments.request,
            runtime_lane=arguments.runtime_lane,
            output_dir=arguments.output_dir,
            timeout_seconds=arguments.timeout_seconds,
            monitor_interval_seconds=arguments.monitor_interval_seconds,
        )
    except Exception as exc:
        arguments.output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            arguments.output_dir / "certification.json",
            {
                "status": "FAILED",
                "phase": "P8_RUNTIME_CERTIFICATION",
                "error_type": type(exc).__name__,
                "message": str(exc),
            },
        )
        write_sha256_manifest(arguments.output_dir, arguments.output_dir / "SHA256SUMS")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
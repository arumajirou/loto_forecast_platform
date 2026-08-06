from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.adapters.timesfm25.contracts import TimesFM25Request  # noqa: E402
from loto.timesfm25_campaign.certification_bundle import (  # noqa: E402
    atomic_write_json,
    atomic_write_text,
    build_certification_report,
    validate_run_id,
    verify_sha256_manifest,
    write_sha256_manifest,
)
from loto.timesfm25_campaign.model_manifest import load_default_manifest  # noqa: E402
from loto.timesfm25_campaign.preflight import (  # noqa: E402
    offline_environment,
    run_preflight,
)

PROVIDER = ROOT / "scripts" / "run_timesfm25_provider.py"
DEFAULT_ENVIRONMENT = ROOT / "environments" / "timesfm25-pytorch"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "timesfm25" / "runtime-certification"


@dataclass
class NvidiaMonitor:
    process: subprocess.Popen[str]
    output: Any
    error: Any


def _capture(command: list[str], *, cwd: Path, timeout: int = 30) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "duration_seconds": time.perf_counter() - started,
        }
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "duration_seconds": time.perf_counter() - started,
        }


def _environment_snapshot(project_root: Path) -> dict[str, Any]:
    commands = {
        "git_head": ["git", "rev-parse", "HEAD"],
        "git_status": ["git", "status", "--short"],
        "uv_version": ["uv", "--version"],
        "nvidia_smi": [
            "nvidia-smi",
            "--query-gpu=uuid,name,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        ],
    }
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "pid": os.getpid(),
        "commands": {
            name: _capture(command, cwd=project_root) for name, command in commands.items()
        },
    }


def _start_nvidia_monitor(run_dir: Path, project_root: Path) -> NvidiaMonitor | None:
    if shutil.which("nvidia-smi") is None:
        return None
    output = (run_dir / "nvidia_process_samples.csv").open("w", encoding="utf-8")
    error = (run_dir / "nvidia_process_monitor.stderr.log").open("w", encoding="utf-8")
    command = [
        "nvidia-smi",
        "--query-compute-apps=timestamp,gpu_uuid,pid,process_name,used_memory",
        "--format=csv,noheader,nounits",
        "--loop-ms=250",
    ]
    try:
        process = subprocess.Popen(
            command,
            cwd=project_root,
            stdout=output,
            stderr=error,
            text=True,
        )
    except OSError:
        output.close()
        error.close()
        return None
    return NvidiaMonitor(process=process, output=output, error=error)


def _stop_nvidia_monitor(monitor: NvidiaMonitor | None) -> None:
    if monitor is None:
        return
    monitor.process.terminate()
    try:
        monitor.process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        monitor.process.kill()
        monitor.process.wait(timeout=10)
    monitor.output.close()
    monitor.error.close()


def _load_response(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "message": f"Invalid provider JSON: {exc}",
        }
    if not isinstance(payload, dict):
        return {
            "status": "ERROR",
            "error_type": "TypeError",
            "message": "Provider response must be a JSON object",
        }
    return payload


def _seal_preflight_failure(
    run_dir: Path,
    request: TimesFM25Request,
    preflight: dict[str, Any],
) -> tuple[Path, int]:
    report = {
        "schema_version": 1,
        "run_id": request.run_id,
        "backend": request.backend.value,
        "repo_id": request.repo_id,
        "revision": request.revision,
        "device_requested": request.device,
        "provider_exit_code": None,
        "timed_out": False,
        "runtime_status": "FAILED",
        "gpu_certification_status": "NOT_EVALUATED",
        "gpu_certification_reasons": [],
        "failure_reason": "PREFLIGHT_FAILED",
        "failed_preflight_checks": preflight["failed_checks"],
    }
    atomic_write_json(run_dir / "runtime_certification.json", report)
    atomic_write_text(run_dir / "status.txt", "FAILED\n")
    manifest = write_sha256_manifest(run_dir)
    manifest_ok, failures = verify_sha256_manifest(run_dir)
    if not manifest_ok:
        raise RuntimeError(f"bundle SHA-256 verification failed: {failures}")
    print(f"RUN_DIR={run_dir}")
    print("STATUS=FAILED")
    print("FAILURE_REASON=PREFLIGHT_FAILED")
    print(f"SHA256_MANIFEST={manifest}")
    print("EXIT_CODE=1")
    return run_dir, 1


def run_certification(args: argparse.Namespace) -> tuple[Path, int]:
    project_root = args.project_root.resolve()
    request_source = args.request.resolve()
    request = TimesFM25Request.model_validate_json(request_source.read_text(encoding="utf-8"))
    run_id = validate_run_id(request.run_id)
    run_dir = args.output_root.resolve() / run_id
    if run_dir.exists():
        raise FileExistsError(
            f"immutable run directory already exists: {run_dir}; use a new run_id"
        )
    run_dir.mkdir(parents=True)
    request_path = run_dir / "provider_request.json"
    response_path = run_dir / "provider_response.json"
    atomic_write_text(request_path, request.model_dump_json(indent=2) + "\n")
    atomic_write_json(run_dir / "environment.json", _environment_snapshot(project_root))

    preflight = run_preflight(
        request,
        environment=args.environment,
        manifest=load_default_manifest(),
        project_root=project_root,
        timeout=min(args.preflight_timeout, args.timeout),
    )
    atomic_write_json(run_dir / "preflight.json", preflight)
    if preflight["status"] != "PASS":
        return _seal_preflight_failure(run_dir, request, preflight)

    command = [
        "uv",
        "run",
        "--project",
        str(args.environment.resolve()),
        "--locked",
        "--offline",
        "python",
        str(PROVIDER),
        "--request",
        str(request_path),
        "--response",
        str(response_path),
    ]
    atomic_write_json(
        run_dir / "command.json",
        {
            "command": command,
            "cwd": str(project_root),
            "timeout_seconds": args.timeout,
            "offline_environment": offline_environment({}),
        },
    )
    monitor = _start_nvidia_monitor(run_dir, project_root)
    started = time.perf_counter()
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=project_root,
            env=offline_environment(),
            capture_output=True,
            text=True,
            timeout=args.timeout,
            check=False,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        stderr += f"\nProvider timed out after {args.timeout} seconds.\n"
    except OSError as exc:
        exit_code = 127
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}\n"
    finally:
        _stop_nvidia_monitor(monitor)

    atomic_write_text(run_dir / "provider.stdout.log", stdout)
    atomic_write_text(run_dir / "provider.stderr.log", stderr)
    atomic_write_text(run_dir / "provider_exit_code.txt", f"{exit_code}\n")
    response_payload = _load_response(response_path)
    report = build_certification_report(
        request,
        response_payload,
        provider_exit_code=exit_code,
        timed_out=timed_out,
    )
    report["orchestrator_duration_seconds"] = time.perf_counter() - started
    atomic_write_json(run_dir / "runtime_certification.json", report)
    atomic_write_text(run_dir / "status.txt", f"{report['runtime_status']}\n")
    manifest = write_sha256_manifest(run_dir)
    manifest_ok, failures = verify_sha256_manifest(run_dir)
    if not manifest_ok:
        raise RuntimeError(f"bundle SHA-256 verification failed: {failures}")

    if report["runtime_status"] in {"VERIFIED_CPU", "VERIFIED_GPU"}:
        result_code = 0
    elif report["runtime_status"] == "PARTIALLY_VERIFIED_GPU":
        result_code = 2
    else:
        result_code = 1
    print(f"RUN_DIR={run_dir}")
    print(f"STATUS={report['runtime_status']}")
    print(f"GPU_CERTIFICATION={report['gpu_certification_status']}")
    print(f"SHA256_MANIFEST={manifest}")
    print(f"EXIT_CODE={result_code}")
    return run_dir, result_code


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run and seal a TimesFM 2.5 runtime certification bundle"
    )
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--environment", type=Path, default=DEFAULT_ENVIRONMENT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--preflight-timeout", type=int, default=300)
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be >= 1")
    if args.preflight_timeout < 1:
        parser.error("--preflight-timeout must be >= 1")
    try:
        _, exit_code = run_certification(args)
    except Exception as exc:
        print("STATUS=FAILED", file=sys.stderr)
        print(f"ERROR_TYPE={type(exc).__name__}", file=sys.stderr)
        print(f"ERROR={exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()

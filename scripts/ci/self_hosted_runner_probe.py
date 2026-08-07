"""Validate a GitHub Actions self-hosted runner and emit JSON evidence."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STATUS_VERIFIED = "VERIFIED"
STATUS_FAILED = "FAILED"


def utc_now() -> str:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC).isoformat()


def run_command(command: list[str], timeout_seconds: int = 30) -> dict[str, Any]:
    """Run a command without a shell and return normalized evidence."""
    executable = shutil.which(command[0])
    if executable is None:
        return {
            "command": command,
            "available": False,
            "returncode": None,
            "stdout": "",
            "stderr": f"command not found: {command[0]}",
        }

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "available": True,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": f"timeout after {timeout_seconds}s",
        }

    return {
        "command": command,
        "available": True,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically so interrupted probes do not leave partial evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def collect_nvidia_smi() -> dict[str, Any]:
    """Collect stable GPU fields from nvidia-smi."""
    query = "index,name,driver_version,memory.total,memory.free,temperature.gpu,power.draw"
    result = run_command(
        [
            "nvidia-smi",
            f"--query-gpu={query}",
            "--format=csv,noheader,nounits",
        ]
    )
    if result["returncode"] != 0:
        return result

    keys = [
        "index",
        "name",
        "driver_version",
        "memory_total_mib",
        "memory_free_mib",
        "temperature_c",
        "power_draw_w",
    ]
    gpus: list[dict[str, str]] = []
    for line in result["stdout"].splitlines():
        values = [value.strip() for value in line.split(",")]
        if len(values) == len(keys):
            gpus.append(dict(zip(keys, values, strict=True)))
    result["gpus"] = gpus
    return result


def collect_torch_probe(require_cuda: bool) -> tuple[dict[str, Any], list[str]]:
    """Execute a real CUDA matrix operation and report failures."""
    failures: list[str] = []
    try:
        import torch
    except Exception as exc:  # pragma: no cover - environment-dependent
        return {"import_error": repr(exc)}, [f"torch import failed: {exc!r}"]

    evidence: dict[str, Any] = {
        "version": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device_count": torch.cuda.device_count(),
    }

    if require_cuda and not torch.cuda.is_available():
        failures.append("CUDA is required but torch.cuda.is_available() is false")
        return evidence, failures

    if not torch.cuda.is_available():
        evidence["execution_device"] = "cpu"
        return evidence, failures

    try:
        device = torch.device("cuda:0")
        before = torch.cuda.memory_allocated(device)
        left = torch.ones((512, 512), dtype=torch.float32, device=device)
        right = torch.full((512, 512), 2.0, dtype=torch.float32, device=device)
        result = left @ right
        torch.cuda.synchronize(device)
        after = torch.cuda.memory_allocated(device)

        finite = bool(torch.isfinite(result).all().item())
        sample = float(result[0, 0].item())
        evidence.update(
            {
                "execution_device": str(result.device),
                "device_name": torch.cuda.get_device_name(device),
                "finite": finite,
                "sample_value": sample,
                "memory_allocated_before_bytes": before,
                "memory_allocated_after_bytes": after,
                "current_process_pid": os.getpid(),
            }
        )

        if result.device.type != "cuda":
            failures.append(f"unexpected execution device: {result.device}")
        if not finite or not math.isfinite(sample):
            failures.append("CUDA result contains non-finite values")
        if sample != 1024.0:
            failures.append(f"unexpected CUDA matrix result: {sample}")
    except Exception as exc:  # pragma: no cover - environment-dependent
        evidence["execution_error"] = repr(exc)
        failures.append(f"CUDA execution failed: {exc!r}")

    return evidence, failures


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-cuda", action="store_true")
    parser.add_argument("--verify-torch", action="store_true")
    parser.add_argument("--require-runner-env", action="store_true")
    parser.add_argument("--min-free-disk-gib", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    return parser


def probe(args: argparse.Namespace) -> dict[str, Any]:
    """Collect runner evidence and determine a formal status."""
    failures: list[str] = []
    warnings: list[str] = []

    runner_env = {
        key: os.getenv(key)
        for key in (
            "GITHUB_REPOSITORY",
            "GITHUB_REF",
            "GITHUB_SHA",
            "GITHUB_ACTOR",
            "GITHUB_RUN_ID",
            "GITHUB_RUN_ATTEMPT",
            "RUNNER_NAME",
            "RUNNER_OS",
            "RUNNER_ARCH",
            "RUNNER_ENVIRONMENT",
        )
    }
    if args.require_runner_env:
        missing = [key for key, value in runner_env.items() if value is None]
        if missing:
            failures.append(f"missing GitHub Actions runner variables: {missing}")

    python_supported = (3, 11) <= sys.version_info[:2] < (3, 14)
    if not python_supported:
        failures.append(f"unsupported Python version: {platform.python_version()}")

    disk = shutil.disk_usage(Path.cwd())
    free_disk_gib = disk.free / (1024**3)
    if free_disk_gib < args.min_free_disk_gib:
        failures.append(
            f"free disk {free_disk_gib:.2f} GiB is below required {args.min_free_disk_gib:.2f} GiB"
        )

    commands = {name: run_command([name, "--version"]) for name in ("git", "uv")}
    for name, result in commands.items():
        if not result["available"] or result["returncode"] != 0:
            failures.append(f"required command unavailable or failing: {name}")

    nvidia_smi = collect_nvidia_smi()
    if args.require_cuda and (
        not nvidia_smi["available"] or nvidia_smi["returncode"] != 0 or not nvidia_smi.get("gpus")
    ):
        failures.append("CUDA is required but nvidia-smi did not report a GPU")
    elif not nvidia_smi["available"]:
        warnings.append("nvidia-smi is unavailable")

    torch_evidence: dict[str, Any] | None = None
    if args.verify_torch:
        torch_evidence, torch_failures = collect_torch_probe(args.require_cuda)
        failures.extend(torch_failures)

    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": STATUS_FAILED if failures else STATUS_VERIFIED,
        "timestamp_utc": utc_now(),
        "failures": failures,
        "warnings": warnings,
        "runner_environment": runner_env,
        "host": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "cwd": str(Path.cwd()),
            "disk_total_gib": round(disk.total / (1024**3), 3),
            "disk_free_gib": round(free_disk_gib, 3),
        },
        "commands": commands,
        "nvidia_smi": nvidia_smi,
        "torch": torch_evidence,
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = build_parser().parse_args(argv)
    payload = probe(args)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        write_json_atomic(args.output, payload)
    return 0 if payload["status"] == STATUS_VERIFIED else 1


if __name__ == "__main__":
    raise SystemExit(main())

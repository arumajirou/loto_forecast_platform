from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

# The exact files the standing directive requires per-file SHA-256 evidence
# for, to catch Ray shipping/caching stale code to a worker process that
# silently diverges from what the driver is actually running.
CODE_FINGERPRINT_FILES = (
    "runner.py",
    "trial_persistence.py",
    "p1_compat.py",
    "persistence.py",
)


def _module_version(module_name: str) -> str | None:
    try:
        module = __import__(module_name)
    except ImportError:
        return None
    return getattr(module, "__version__", None)


def code_environment_fingerprint() -> dict[str, Any]:
    """Capture code identity + interpreter environment for driver/worker comparison.

    Must be called from within `src/loto/auto_campaign` (this module's own
    directory) so the four fingerprinted files are resolved relative to the
    actual package on `sys.path`, not a stale copy Ray may have shipped
    elsewhere.
    """

    package_dir = Path(__file__).resolve().parent
    file_sha256 = {
        name: hashlib.sha256((package_dir / name).read_bytes()).hexdigest()
        for name in CODE_FINGERPRINT_FILES
    }

    import loto

    return {
        "pid": os.getpid(),
        "python_executable": sys.executable,
        "sys_path": list(sys.path),
        "loto_package_path": str(Path(loto.__file__).resolve()),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "file_sha256": file_sha256,
        "neuralforecast_version": _module_version("neuralforecast"),
        "ray_version": _module_version("ray"),
        "torch_version": _module_version("torch"),
    }


def compare_code_fingerprints(driver: dict[str, Any], worker: dict[str, Any]) -> dict[str, Any]:
    """Compare a driver-captured and worker-captured `code_environment_fingerprint()`.

    `pid` and `cuda_visible_devices` are captured for audit but intentionally
    excluded from the mismatch gate: a worker process, by construction, has a
    different PID than the driver, and Ray may legitimately assign a
    different `CUDA_VISIBLE_DEVICES` value per trial actor. Treating either
    as a required match would manufacture a false FAIL unrelated to the
    actual defect this check exists to catch -- the worker silently
    executing different code or a different package install than the
    driver.

    `python_executable`, `sys_path`, and `loto_package_path` are captured for
    audit but excluded from the mismatch gate for the same reason: under the
    Ray backend, `runtime_env.working_dir` stages a session-specific copy of
    the project into a temp directory before launching the worker, so these
    paths are guaranteed to differ from the driver's even when the worker is
    running byte-identical code from a byte-identical package install. The
    `file_sha256` digests (plus the installed package versions below) are
    what actually detect a worker silently running different code.
    """

    identity_keys = (
        "neuralforecast_version",
        "ray_version",
        "torch_version",
    )
    mismatches: list[str] = []
    for name, digest in driver.get("file_sha256", {}).items():
        if worker.get("file_sha256", {}).get(name) != digest:
            mismatches.append(f"file_sha256[{name}]")
    for key in identity_keys:
        if driver.get(key) != worker.get(key):
            mismatches.append(key)
    return {
        "status": "PASS" if not mismatches else "FAIL",
        "mismatches": mismatches,
        "driver": driver,
        "worker": worker,
    }


def _is_wsl() -> bool:
    """Return whether the current Linux kernel is hosted by WSL/WSL2."""

    release = platform.release().lower()
    version = platform.version().lower()
    return "microsoft" in release or "wsl" in release or "microsoft" in version


def _process_local_cuda_snapshot() -> dict[str, Any]:
    """Bind CUDA allocation evidence to the current Python process.

    NVIDIA documents that NVML/nvidia-smi does not expose every active compute
    process query under WSL.  When the external process list is unavailable,
    positive CUDA memory owned by this exact Python PID is the fail-closed
    process-local fallback.  It is never used to verify a different PID.
    """

    payload: dict[str, Any] = {
        "pid": os.getpid(),
        "torch_available": False,
        "cuda_available": False,
        "cuda_current_device": None,
        "cuda_memory_allocated": 0,
        "cuda_memory_reserved": 0,
        "cuda_peak_memory_allocated": 0,
        "cuda_context_active": False,
    }
    try:
        import torch
    except ImportError:
        return payload

    payload["torch_available"] = True
    try:
        cuda_available = bool(torch.cuda.is_available())
        payload["cuda_available"] = cuda_available
        if not cuda_available:
            return payload
        payload["cuda_current_device"] = int(torch.cuda.current_device())
        payload["cuda_memory_allocated"] = int(torch.cuda.memory_allocated())
        payload["cuda_memory_reserved"] = int(torch.cuda.memory_reserved())
        payload["cuda_peak_memory_allocated"] = int(torch.cuda.max_memory_allocated())
        payload["cuda_context_active"] = any(
            int(payload[key]) > 0
            for key in (
                "cuda_memory_allocated",
                "cuda_memory_reserved",
                "cuda_peak_memory_allocated",
            )
        )
    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}"
    return payload


def gpu_process_snapshot(pid: int | None = None) -> dict[str, Any]:
    """Verify GPU execution for a PID with a WSL-aware fail-closed fallback.

    Native Linux requires an explicit `nvidia-smi --query-compute-apps` PID
    match.  WSL may return an empty active-compute-process list even while a
    CUDA workload is running.  Only in WSL, only for the current Python PID,
    and only with positive process-local CUDA memory do we accept a PyTorch
    CUDA-context proof instead.  The verification method and limitation are
    persisted so external and fallback evidence remain distinguishable.
    """

    target_pid = os.getpid() if pid is None else pid
    command = [
        "nvidia-smi",
        "--query-compute-apps=pid,process_name,used_memory",
        "--format=csv,noheader,nounits",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    rows = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    matches = [row for row in rows if row.split(",", 1)[0].strip() == str(target_pid)]

    verified = bool(matches)
    method = "nvidia_smi_compute_apps" if verified else "none"
    limitation = None
    local_cuda: dict[str, Any] = {}
    wsl = _is_wsl()

    if not verified and wsl and target_pid == os.getpid():
        local_cuda = _process_local_cuda_snapshot()
        if bool(local_cuda.get("cuda_context_active")):
            verified = True
            method = "torch_process_local_cuda_context"
            limitation = "wsl_nvidia_smi_active_compute_process_query_unavailable"

    return {
        "pid": target_pid,
        "returncode": result.returncode,
        "gpu_pid_verified": verified,
        "verification_method": method,
        "platform_wsl": wsl,
        "nvidia_smi_rows": matches,
        "rows": matches,
        "limitation": limitation,
        "process_local_cuda": local_cuda,
    }


def torch_runtime_snapshot(model: Any | None = None) -> dict[str, Any]:
    try:
        import torch
    except ImportError:
        return {"torch_available": False, "pid": os.getpid()}

    parameter_device = None
    trainer_root_device = None
    if model is not None:
        try:
            parameter_device = str(next(model.parameters()).device)
        except (StopIteration, AttributeError):
            pass
        trainer = getattr(model, "_trainer", None)
        root = getattr(getattr(trainer, "strategy", None), "root_device", None)
        trainer_root_device = None if root is None else str(root)
    return {
        "torch_available": True,
        "pid": os.getpid(),
        "cuda_available": torch.cuda.is_available(),
        "cuda_device_count": torch.cuda.device_count(),
        "cuda_device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "cuda_memory_allocated": int(torch.cuda.memory_allocated())
        if torch.cuda.is_available()
        else 0,  # noqa: E501
        "cuda_memory_reserved": int(torch.cuda.memory_reserved())
        if torch.cuda.is_available()
        else 0,  # noqa: E501
        "cuda_peak_memory_allocated": int(torch.cuda.max_memory_allocated())
        if torch.cuda.is_available()
        else 0,  # noqa: E501
        "parameter_device": parameter_device,
        "trainer_root_device": trainer_root_device,
    }

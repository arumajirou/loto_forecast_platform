from __future__ import annotations

import hashlib
import os
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


def gpu_process_snapshot(pid: int | None = None) -> dict[str, Any]:
    pid = os.getpid() if pid is None else pid
    command = [
        "nvidia-smi",
        "--query-compute-apps=pid,process_name,used_memory",
        "--format=csv,noheader,nounits",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    rows = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    matches = [row for row in rows if row.split(",", 1)[0].strip() == str(pid)]
    return {
        "pid": pid,
        "returncode": result.returncode,
        "gpu_pid_verified": bool(matches),
        "rows": matches,
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

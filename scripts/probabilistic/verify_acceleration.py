from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from loto.probabilistic.config import load_run_config
from loto.probabilistic.planner import build_plan, plan_summary
from loto.probabilistic.resources import ProbabilisticResourcePolicy


def nvidia_info() -> dict[str, object]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {"available": True, "lines": result.stdout.strip().splitlines()}
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="configs/probabilistic/native_fast_gpu_dashboard.yaml",
    )
    args = parser.parse_args()
    config = load_run_config(Path(args.config))
    summary = plan_summary(config)
    policy = ProbabilisticResourcePolicy(
        outer_workers=config.outer_workers,
        max_heavy_cpu_jobs=config.max_heavy_cpu_jobs,
        max_gpu_jobs=config.max_gpu_jobs,
        gpu_priority=config.gpu_priority,
        gpu_backends=tuple(config.gpu_backends),
        native_device=config.native_device,
    )
    effective: dict[str, int] = {}
    for trial in build_plan(config):
        if not trial.allowed:
            continue
        resource = policy.effective_resource(trial)
        effective[resource] = effective.get(resource, 0) + 1
    payload: dict[str, object] = {
        "config": str(Path(args.config).resolve()),
        "outer_workers": config.outer_workers,
        "max_heavy_cpu_jobs": config.max_heavy_cpu_jobs,
        "max_gpu_jobs": config.max_gpu_jobs,
        "gpu_priority": config.gpu_priority,
        "gpu_backends": config.gpu_backends,
        "native_device": config.native_device,
        "native_inner_cores": config.native_inner_cores,
        "declared_plan_by_resource": summary["by_resource"],
        "effective_plan_by_resource": dict(sorted(effective.items())),
        "nvidia": nvidia_info(),
    }

    try:
        import torch

        payload["torch"] = {
            "version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": torch.version.cuda,
            "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        }
    except Exception as exc:
        payload["torch"] = {"error": f"{type(exc).__name__}: {exc}"}

    try:
        import jax

        try:
            gpu_devices = [str(device) for device in jax.devices("gpu")]
        except Exception:
            gpu_devices = []
        payload["jax"] = {
            "version": jax.__version__,
            "default_backend": jax.default_backend(),
            "gpu_devices": gpu_devices,
            "all_devices": [str(device) for device in jax.devices()],
        }
    except Exception as exc:
        payload["jax"] = {"error": f"{type(exc).__name__}: {exc}"}

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    errors: list[str] = []
    if config.outer_workers != 8:
        errors.append("outer_workers must be 8")
    if config.native_inner_cores != 1:
        errors.append("native_inner_cores must be 1")
    if config.native_device == "cuda":
        if not bool((payload.get("nvidia") or {}).get("available")):  # type: ignore[union-attr]
            errors.append("nvidia-smi unavailable")
        torch_info = payload.get("torch") or {}
        jax_info = payload.get("jax") or {}
        if "pyro" in config.gpu_backends and not bool(torch_info.get("cuda_available")):  # type: ignore[union-attr]
            errors.append("Pyro requested on GPU but torch CUDA is unavailable")
        if "numpyro" in config.gpu_backends and not list(jax_info.get("gpu_devices") or []):  # type: ignore[union-attr]
            errors.append("NumPyro requested on GPU but JAX GPU is unavailable")
    if errors:
        for error in errors:
            print(f"ACCELERATION_ERROR: {error}")
        return 2
    print("ACCELERATION_PREFLIGHT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

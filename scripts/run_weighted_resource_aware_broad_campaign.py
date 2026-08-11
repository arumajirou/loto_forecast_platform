#!/usr/bin/env python
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

from loto.models.catalog_full import build_catalog
from loto.orchestration.process_observer import run_monitored_process
from loto.orchestration.weighted_resource_scheduler import (
    WeightedResourceLease,
    WeightedResourceScheduler,
    configure_weighted_profiles,
    weighted_runtime_resource_class,
)

ROOT = Path(__file__).resolve().parents[1]
BASE_RUNNER = ROOT / "scripts" / "run_resource_aware_broad_campaign.py"
DEFAULT_BASE_GPU_SLOT_MIB = 2048
_ACTIVE_TASK = threading.local()


def _load_base_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("loto_weighted_base_runner", BASE_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load base runner: {BASE_RUNNER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _has_option(argv: list[str], option: str) -> bool:
    return option in argv or any(item.startswith(f"{option}=") for item in argv)


def _inject_weighted_defaults(argv: list[str]) -> list[str]:
    resolved = list(argv)
    if not _has_option(resolved, "--gpu-slot-mib"):
        resolved.extend(["--gpu-slot-mib", str(DEFAULT_BASE_GPU_SLOT_MIB)])
    return resolved


class ObservedWeightedResourceScheduler(WeightedResourceScheduler):
    """Weighted scheduler that binds the acquired lease to its worker thread."""

    def acquire(
        self,
        *,
        requires_gpu: bool,
        lease_id: str,
        timeout: float | None = None,
        exclusive_gpu: bool = False,
    ) -> WeightedResourceLease:
        lease = super().acquire(
            requires_gpu=requires_gpu,
            lease_id=lease_id,
            timeout=timeout,
            exclusive_gpu=exclusive_gpu,
        )
        _ACTIVE_TASK.lease = lease
        return lease


def _write_process_observation(cwd: str | Path, payload: dict[str, Any]) -> None:
    path = Path(cwd).parent / "PROCESS_OBSERVATION.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _attach_child_pid(pid: int) -> None:
    lease = getattr(_ACTIVE_TASK, "lease", None)
    if lease is not None:
        lease.child_pid = pid


def _device_evidence(*, resource_class: str, observation: dict[str, Any]) -> dict[str, Any]:
    requires_gpu = resource_class != "CPU"
    gpu_pids = [int(pid) for pid in observation.get("gpu_pids", [])]
    attribution_available = bool(observation.get("gpu_attribution_available", False))
    if not requires_gpu:
        fallback_status = "NOT_APPLICABLE_CPU_CONTRACT"
    elif gpu_pids:
        fallback_status = "NOT_OBSERVED_GPU_PID_ATTRIBUTED"
    elif attribution_available:
        fallback_status = "UNRESOLVED_NO_MATCHED_GPU_PID"
    else:
        fallback_status = "UNRESOLVED_GPU_ATTRIBUTION_UNAVAILABLE"
    return {
        "requested_device": "cuda" if requires_gpu else "cpu",
        "gpu_pids": gpu_pids,
        "gpu_attribution_available": attribution_available,
        "cpu_fallback_status": fallback_status,
    }


class _SubprocessProxy:
    TimeoutExpired = subprocess.TimeoutExpired

    def run(
        self,
        command: Any,
        *,
        cwd: str | Path | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: float | None = None,
        check: bool = False,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[Any]:
        lease = getattr(_ACTIVE_TASK, "lease", None)
        if lease is None or cwd is None or not capture_output:
            return subprocess.run(
                command,
                cwd=cwd,
                capture_output=capture_output,
                text=text,
                timeout=timeout,
                check=check,
                **kwargs,
            )

        effective_timeout = float(timeout if timeout is not None else 3600.0)
        monitored = run_monitored_process(
            command,
            cwd=cwd,
            timeout=effective_timeout,
            on_start=_attach_child_pid,
        )
        observation = monitored.observation.to_dict()
        _ACTIVE_TASK.process_observation = observation
        _write_process_observation(cwd, observation)

        stdout: Any = monitored.stdout if text else monitored.stdout.encode()
        stderr: Any = monitored.stderr if text else monitored.stderr.encode()
        if monitored.timed_out:
            raise subprocess.TimeoutExpired(
                command,
                effective_timeout,
                output=stdout,
                stderr=stderr,
            )

        completed = subprocess.CompletedProcess(
            args=command,
            returncode=int(monitored.returncode or 0),
            stdout=stdout,
            stderr=stderr,
        )
        if check and completed.returncode != 0:
            raise subprocess.CalledProcessError(
                completed.returncode,
                command,
                output=stdout,
                stderr=stderr,
            )
        return completed


def _install_observation_hooks(base: ModuleType) -> None:
    dynamic_base: Any = base
    original_run_task = dynamic_base._run_task

    def observed_run_task(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            result = original_run_task(*args, **kwargs)
            attempt_dir = Path(result["attempt_dir"])
            observation_path = attempt_dir / "PROCESS_OBSERVATION.json"
            if observation_path.exists():
                observation = json.loads(observation_path.read_text(encoding="utf-8"))
                result["process_observation"] = observation
                result["device_evidence"] = _device_evidence(
                    resource_class=str(result["resource_class"]),
                    observation=observation,
                )
                dynamic_base._atomic_json(attempt_dir.parent / "FINAL.json", result)
            return result
        finally:
            for attribute in ("lease", "process_observation"):
                if hasattr(_ACTIVE_TASK, attribute):
                    delattr(_ACTIVE_TASK, attribute)

    dynamic_base.ResourceScheduler = ObservedWeightedResourceScheduler
    dynamic_base.runtime_resource_class = weighted_runtime_resource_class
    dynamic_base.subprocess = _SubprocessProxy()
    dynamic_base._run_task = observed_run_task


def main(argv: list[str] | None = None) -> int:
    base = _load_base_runner()

    # Configure the profile registry from the same broad catalog the base runner uses,
    # then replace only scheduling/process-observation hooks. Model/evaluation semantics
    # remain the existing audited campaign implementation.
    configure_weighted_profiles(build_catalog())
    _install_observation_hooks(base)

    resolved_argv = _inject_weighted_defaults(list(sys.argv[1:] if argv is None else argv))
    return int(base.main(resolved_argv))


if __name__ == "__main__":
    raise SystemExit(main())

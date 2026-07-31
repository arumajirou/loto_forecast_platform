from __future__ import annotations

# ruff: noqa: E501
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResourcePolicy:
    max_parallel_cpu_models: int = 4
    max_parallel_gpu_models: int = 1
    cpus_per_trial: int = 1
    gpus_per_trial: int = 0
    max_vram_mib: int | None = None
    gpu_memory_safety_margin_mib: int = 1024
    timeout_seconds: int = 1800
    retry_count: int = 0
    retry_backoff: float = 2.0


@dataclass
class ResourceLease:
    lease_id: str
    kind: str
    started_at: float
    pid: int = field(default_factory=os.getpid)
    released_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "kind": self.kind,
            "pid": self.pid,
            "started_at": self.started_at,
            "released_at": self.released_at,
        }


class ResourceScheduler:
    def __init__(self, policy: ResourcePolicy):
        if policy.max_parallel_cpu_models < 1:
            raise ValueError("max_parallel_cpu_models must be >= 1")
        if policy.max_parallel_gpu_models < 0:
            raise ValueError("max_parallel_gpu_models must be >= 0")
        self.policy = policy
        self._cpu = threading.BoundedSemaphore(policy.max_parallel_cpu_models)
        self._gpu = threading.BoundedSemaphore(max(1, policy.max_parallel_gpu_models))
        self._lock = threading.Lock()
        self._leases: list[ResourceLease] = []
        self._active_gpu_trials = 0

    def gpu_resource_status(self, *, estimated_vram_mib: int | None = None) -> dict[str, Any]:
        free_vram_mib: int | None = None
        try:
            proc = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                free_vram_mib = int(proc.stdout.strip().splitlines()[0])
        except Exception:
            free_vram_mib = None
        estimated = (
            estimated_vram_mib if estimated_vram_mib is not None else self.policy.max_vram_mib
        )
        with self._lock:
            active_gpu_trials = self._active_gpu_trials
        enough_slots = active_gpu_trials < self.policy.max_parallel_gpu_models
        enough_vram = (
            free_vram_mib is None
            or estimated is None
            or free_vram_mib - self.policy.gpu_memory_safety_margin_mib >= estimated
        )
        return {
            "free_vram_mib": free_vram_mib,
            "reserved_vram_mib": estimated,
            "running_gpu_trials": active_gpu_trials,
            "max_parallel_gpu_models": self.policy.max_parallel_gpu_models,
            "estimated_vram_mib": estimated,
            "safety_margin_mib": self.policy.gpu_memory_safety_margin_mib,
            "decision": "AVAILABLE" if enough_slots and enough_vram else "WAITING_FOR_GPU_RESOURCE",
        }

    def acquire(
        self, *, requires_gpu: bool, lease_id: str, timeout: float | None = None
    ) -> ResourceLease:
        semaphore = self._gpu if requires_gpu else self._cpu
        if requires_gpu and self.policy.max_parallel_gpu_models == 0:
            raise RuntimeError("GPU trial requested but max_parallel_gpu_models is 0")
        ok = semaphore.acquire(
            timeout=timeout if timeout is not None else self.policy.timeout_seconds
        )
        if not ok:
            raise TimeoutError(f"resource lease timed out: {lease_id}")
        lease = ResourceLease(
            lease_id=lease_id, kind="gpu" if requires_gpu else "cpu", started_at=time.time()
        )
        with self._lock:
            if requires_gpu:
                self._active_gpu_trials += 1
            self._leases.append(lease)
        return lease

    def release(self, lease: ResourceLease) -> None:
        lease.released_at = time.time()
        if lease.kind == "gpu":
            with self._lock:
                self._active_gpu_trials = max(0, self._active_gpu_trials - 1)
            self._gpu.release()
        else:
            self._cpu.release()

    def report(self) -> list[dict[str, Any]]:
        with self._lock:
            return [lease.to_dict() for lease in self._leases]

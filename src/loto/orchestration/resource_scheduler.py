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


@dataclass(frozen=True)
class ResourceSnapshot:
    logical_cpus: int
    available_ram_mib: int
    gpu_count: int
    gpu_total_mib: tuple[int, ...] = ()
    gpu_free_mib: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "logical_cpus": self.logical_cpus,
            "available_ram_mib": self.available_ram_mib,
            "gpu_count": self.gpu_count,
            "gpu_total_mib": list(self.gpu_total_mib),
            "gpu_free_mib": list(self.gpu_free_mib),
        }


@dataclass(frozen=True)
class ResolvedResourcePlan:
    parallel_cpu_models: int
    parallel_gpu_models: int
    parallel_exclusive_gpu_models: int
    cpus_per_trial: int
    gpu_slot_mib: int
    safety_margin_mib: int
    outer_worker_cap: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "parallel_cpu_models": self.parallel_cpu_models,
            "parallel_gpu_models": self.parallel_gpu_models,
            "parallel_exclusive_gpu_models": self.parallel_exclusive_gpu_models,
            "cpus_per_trial": self.cpus_per_trial,
            "gpu_slot_mib": self.gpu_slot_mib,
            "safety_margin_mib": self.safety_margin_mib,
            "outer_worker_cap": self.outer_worker_cap,
        }


def _available_ram_mib() -> int:
    try:
        with open("/proc/meminfo", encoding="utf-8") as stream:
            for line in stream:
                if line.startswith("MemAvailable:"):
                    return max(0, int(line.split()[1]) // 1024)
    except (OSError, ValueError, IndexError):
        pass
    return 0


def _gpu_memory_snapshot() -> tuple[tuple[int, ...], tuple[int, ...]]:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0:
            return (), ()
        totals: list[int] = []
        frees: list[int] = []
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            total, free = (int(part.strip()) for part in line.split(",", maxsplit=1))
            totals.append(total)
            frees.append(free)
        return tuple(totals), tuple(frees)
    except (OSError, ValueError, subprocess.SubprocessError):
        return (), ()


def collect_resource_snapshot() -> ResourceSnapshot:
    """Capture live CPU/RAM/GPU capacity used by runtime-audit scheduling."""

    totals, frees = _gpu_memory_snapshot()
    return ResourceSnapshot(
        logical_cpus=max(1, int(os.cpu_count() or 1)),
        available_ram_mib=_available_ram_mib(),
        gpu_count=len(totals),
        gpu_total_mib=totals,
        gpu_free_mib=frees,
    )


def resolve_resource_plan(
    snapshot: ResourceSnapshot,
    *,
    outer_worker_cap: int = 8,
    cpus_per_trial: int = 2,
    ram_per_cpu_job_mib: int = 6144,
    gpu_slot_mib: int = 5120,
    safety_margin_mib: int = 2048,
) -> ResolvedResourcePlan:
    """Derive conservative CPU/GPU outer concurrency from live resources.

    The plan is intentionally capacity based rather than model-count based. Heavy models
    still use the exclusive-GPU lane; ordinary GPU jobs consume one estimated slot.
    """

    if outer_worker_cap < 1:
        raise ValueError("outer_worker_cap must be >= 1")
    if cpus_per_trial < 1:
        raise ValueError("cpus_per_trial must be >= 1")
    if ram_per_cpu_job_mib < 1:
        raise ValueError("ram_per_cpu_job_mib must be >= 1")
    if gpu_slot_mib < 1:
        raise ValueError("gpu_slot_mib must be >= 1")
    if safety_margin_mib < 0:
        raise ValueError("safety_margin_mib must be >= 0")

    cpu_by_threads = max(1, snapshot.logical_cpus // cpus_per_trial)
    if snapshot.available_ram_mib > 0:
        cpu_by_ram = max(1, snapshot.available_ram_mib // ram_per_cpu_job_mib)
    else:
        cpu_by_ram = cpu_by_threads
    cpu_workers = min(outer_worker_cap, cpu_by_threads, cpu_by_ram)

    gpu_workers = 0
    if snapshot.gpu_count > 0:
        per_gpu_slots = []
        for free_mib in snapshot.gpu_free_mib:
            usable = max(0, free_mib - safety_margin_mib)
            per_gpu_slots.append(usable // gpu_slot_mib)
        gpu_workers = min(outer_worker_cap, sum(per_gpu_slots)) if per_gpu_slots else 0

    if cpu_workers + gpu_workers > outer_worker_cap:
        cpu_workers = max(1, outer_worker_cap - gpu_workers)

    return ResolvedResourcePlan(
        parallel_cpu_models=cpu_workers,
        parallel_gpu_models=gpu_workers,
        parallel_exclusive_gpu_models=1 if gpu_workers > 0 else 0,
        cpus_per_trial=cpus_per_trial,
        gpu_slot_mib=gpu_slot_mib,
        safety_margin_mib=safety_margin_mib,
        outer_worker_cap=outer_worker_cap,
    )


def runtime_resource_class(
    *,
    model_id: str,
    library: str,
    class_name: str = "",
    capabilities: tuple[str, ...] = (),
) -> str:
    """Return a scheduling class without making a runtime-success claim."""

    normalized = model_id.lower()
    if normalized == "nf-timellm" or class_name == "TimeLLM":
        return "EXCLUSIVE_GPU"
    if library in {"neuralforecast", "neuralforecast_auto"}:
        return "GPU"
    if "gpu" in capabilities or "gpu_optional" in capabilities or "zero_shot" in capabilities:
        return "GPU"
    return "CPU"


@dataclass
class ResourceLease:
    lease_id: str
    kind: str
    started_at: float
    pid: int = field(default_factory=os.getpid)
    released_at: float | None = None
    slots: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "kind": self.kind,
            "pid": self.pid,
            "started_at": self.started_at,
            "released_at": self.released_at,
            "slots": self.slots,
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
        self._exclusive_gpu_lock = threading.Lock()
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
        self,
        *,
        requires_gpu: bool,
        lease_id: str,
        timeout: float | None = None,
        exclusive_gpu: bool = False,
    ) -> ResourceLease:
        lease_timeout = timeout if timeout is not None else self.policy.timeout_seconds
        if requires_gpu and self.policy.max_parallel_gpu_models == 0:
            raise RuntimeError("GPU trial requested but max_parallel_gpu_models is 0")

        if requires_gpu and exclusive_gpu:
            if not self._exclusive_gpu_lock.acquire(timeout=lease_timeout):
                raise TimeoutError(f"exclusive GPU lease timed out: {lease_id}")
            acquired = 0
            try:
                deadline = time.monotonic() + lease_timeout
                for _ in range(self.policy.max_parallel_gpu_models):
                    remaining = max(0.0, deadline - time.monotonic())
                    if not self._gpu.acquire(timeout=remaining):
                        raise TimeoutError(f"exclusive GPU lease timed out: {lease_id}")
                    acquired += 1
            except BaseException:
                for _ in range(acquired):
                    self._gpu.release()
                self._exclusive_gpu_lock.release()
                raise
            lease = ResourceLease(
                lease_id=lease_id,
                kind="gpu-exclusive",
                started_at=time.time(),
                slots=max(1, self.policy.max_parallel_gpu_models),
            )
            with self._lock:
                self._active_gpu_trials += lease.slots
                self._leases.append(lease)
            return lease

        semaphore = self._gpu if requires_gpu else self._cpu
        ok = semaphore.acquire(timeout=lease_timeout)
        if not ok:
            raise TimeoutError(f"resource lease timed out: {lease_id}")
        lease = ResourceLease(
            lease_id=lease_id,
            kind="gpu" if requires_gpu else "cpu",
            started_at=time.time(),
        )
        with self._lock:
            if requires_gpu:
                self._active_gpu_trials += 1
            self._leases.append(lease)
        return lease

    def release(self, lease: ResourceLease) -> None:
        lease.released_at = time.time()
        if lease.kind == "gpu-exclusive":
            with self._lock:
                self._active_gpu_trials = max(0, self._active_gpu_trials - lease.slots)
            for _ in range(lease.slots):
                self._gpu.release()
            self._exclusive_gpu_lock.release()
        elif lease.kind == "gpu":
            with self._lock:
                self._active_gpu_trials = max(0, self._active_gpu_trials - 1)
            self._gpu.release()
        else:
            self._cpu.release()

    def report(self) -> list[dict[str, Any]]:
        with self._lock:
            return [lease.to_dict() for lease in self._leases]

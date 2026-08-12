from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ResolvedResourcePlan",
    "ResourceLease",
    "ResourcePolicy",
    "ResourceScheduler",
    "ResourceSnapshot",
    "collect_resource_snapshot",
    "resolve_resource_plan",
    "runtime_resource_class",
]


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
    gpu_device_slots: tuple[int, ...] = ()


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
    gpu_device_slots: tuple[int, ...] = ()
    executor_mode: str = "shared_outer_pool"

    def to_dict(self) -> dict[str, Any]:
        return {
            "parallel_cpu_models": self.parallel_cpu_models,
            "parallel_gpu_models": self.parallel_gpu_models,
            "parallel_exclusive_gpu_models": self.parallel_exclusive_gpu_models,
            "cpus_per_trial": self.cpus_per_trial,
            "gpu_slot_mib": self.gpu_slot_mib,
            "safety_margin_mib": self.safety_margin_mib,
            "outer_worker_cap": self.outer_worker_cap,
            "gpu_device_slots": list(self.gpu_device_slots),
            "executor_mode": self.executor_mode,
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


def _limit_gpu_device_slots(per_gpu_slots: list[int], limit: int) -> tuple[int, ...]:
    """Distribute admitted GPU slots across physical devices round-robin."""
    admitted = [0 for _ in per_gpu_slots]
    remaining = max(0, limit)
    while remaining:
        progressed = False
        for device_index, capacity in enumerate(per_gpu_slots):
            if remaining == 0:
                break
            if admitted[device_index] >= capacity:
                continue
            admitted[device_index] += 1
            remaining -= 1
            progressed = True
        if not progressed:
            break
    return tuple(admitted)


def resolve_resource_plan(
    snapshot: ResourceSnapshot,
    *,
    outer_worker_cap: int = 8,
    cpus_per_trial: int = 2,
    ram_per_cpu_job_mib: int = 6144,
    gpu_slot_mib: int = 5120,
    safety_margin_mib: int = 2048,
) -> ResolvedResourcePlan:
    """Derive CPU/GPU lane limits under a shared outer executor cap.

    CPU/GPU values are lane admission limits. The campaign runner enforces the actual
    total concurrency with one shared executor bounded by ``outer_worker_cap``. GPU
    capacity remains attached to explicit physical device indexes; aggregate capacity
    is never silently treated as GPU-0 capacity.
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
    cpu_capacity = min(outer_worker_cap, cpu_by_threads, cpu_by_ram)

    per_gpu_slots: list[int] = []
    if snapshot.gpu_count > 0:
        for free_mib in snapshot.gpu_free_mib:
            usable = max(0, free_mib - safety_margin_mib)
            per_gpu_slots.append(usable // gpu_slot_mib)
    raw_gpu_workers = sum(per_gpu_slots)

    if raw_gpu_workers == 0:
        gpu_workers = 0
        cpu_workers = cpu_capacity
    elif outer_worker_cap == 1:
        # The single shared executor slot alternates CPU/GPU work, so neither lane is
        # disabled merely because the other lane exists.
        gpu_workers = 1
        cpu_workers = 1
    else:
        # Reserve at least one outer slot for CPU work in the mixed broad campaign.
        gpu_workers = min(raw_gpu_workers, outer_worker_cap - 1)
        cpu_workers = min(cpu_capacity, outer_worker_cap - gpu_workers)

    gpu_device_slots = _limit_gpu_device_slots(per_gpu_slots, gpu_workers)
    gpu_workers = sum(gpu_device_slots)
    return ResolvedResourcePlan(
        parallel_cpu_models=cpu_workers,
        parallel_gpu_models=gpu_workers,
        parallel_exclusive_gpu_models=1 if gpu_workers > 0 else 0,
        cpus_per_trial=cpus_per_trial,
        gpu_slot_mib=gpu_slot_mib,
        safety_margin_mib=safety_margin_mib,
        outer_worker_cap=outer_worker_cap,
        gpu_device_slots=gpu_device_slots,
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
    gpu_device_index: int | None = None
    gpu_device_indices: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "kind": self.kind,
            "pid": self.pid,
            "started_at": self.started_at,
            "released_at": self.released_at,
            "slots": self.slots,
            "gpu_device_index": self.gpu_device_index,
            "gpu_device_indices": list(self.gpu_device_indices),
        }


class ResourceScheduler:
    def __init__(self, policy: ResourcePolicy):
        if policy.max_parallel_cpu_models < 1:
            raise ValueError("max_parallel_cpu_models must be >= 1")
        if policy.max_parallel_gpu_models < 0:
            raise ValueError("max_parallel_gpu_models must be >= 0")
        self.policy = policy
        self._cpu = threading.BoundedSemaphore(policy.max_parallel_cpu_models)

        device_slots = policy.gpu_device_slots
        if not device_slots and policy.max_parallel_gpu_models > 0:
            device_slots = (policy.max_parallel_gpu_models,)
        if any(slots < 0 for slots in device_slots):
            raise ValueError("gpu_device_slots must be >= 0")
        if sum(device_slots) != policy.max_parallel_gpu_models:
            raise ValueError("sum(gpu_device_slots) must equal max_parallel_gpu_models")

        self._gpu_device_slots = tuple(device_slots)
        self._gpu_devices: tuple[threading.BoundedSemaphore | None, ...] = tuple(
            threading.BoundedSemaphore(slots) if slots > 0 else None for slots in device_slots
        )
        self._exclusive_gpu_gate = threading.Lock()
        self._lock = threading.Lock()
        self._leases: list[ResourceLease] = []
        self._active_gpu_trials = 0
        self._active_gpu_by_device = [0 for _ in device_slots]
        self._next_gpu_device = 0

    def gpu_resource_status(self, *, estimated_vram_mib: int | None = None) -> dict[str, Any]:
        free_vram_mib: list[int] | None = None
        try:
            proc = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                free_vram_mib = [
                    int(line.strip()) for line in proc.stdout.splitlines() if line.strip()
                ]
        except Exception:
            free_vram_mib = None
        estimated = (
            estimated_vram_mib if estimated_vram_mib is not None else self.policy.max_vram_mib
        )
        with self._lock:
            active_gpu_trials = self._active_gpu_trials
            active_by_device = list(self._active_gpu_by_device)
        enough_slots = active_gpu_trials < self.policy.max_parallel_gpu_models
        enough_vram = True
        if free_vram_mib is not None and estimated is not None:
            enough_vram = any(
                free_mib - self.policy.gpu_memory_safety_margin_mib >= estimated
                for free_mib in free_vram_mib
            )
        return {
            "free_vram_mib": free_vram_mib,
            "reserved_vram_mib": estimated,
            "running_gpu_trials": active_gpu_trials,
            "running_gpu_trials_by_device": active_by_device,
            "gpu_device_slots": list(self._gpu_device_slots),
            "max_parallel_gpu_models": self.policy.max_parallel_gpu_models,
            "estimated_vram_mib": estimated,
            "safety_margin_mib": self.policy.gpu_memory_safety_margin_mib,
            "decision": "AVAILABLE" if enough_slots and enough_vram else "WAITING_FOR_GPU_RESOURCE",
        }

    def _acquire_gpu_device(self, *, deadline: float, lease_id: str) -> int:
        device_count = len(self._gpu_devices)
        while True:
            with self._lock:
                start = self._next_gpu_device
            for offset in range(device_count):
                device_index = (start + offset) % device_count
                semaphore = self._gpu_devices[device_index]
                if semaphore is None or not semaphore.acquire(blocking=False):
                    continue
                with self._lock:
                    self._next_gpu_device = (device_index + 1) % max(1, device_count)
                    self._active_gpu_trials += 1
                    self._active_gpu_by_device[device_index] += 1
                return device_index
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"resource lease timed out: {lease_id}")
            time.sleep(min(0.01, remaining))

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
            if not self._exclusive_gpu_gate.acquire(timeout=lease_timeout):
                raise TimeoutError(f"exclusive GPU lease timed out: {lease_id}")
            acquired_devices: list[int] = []
            try:
                deadline = time.monotonic() + lease_timeout
                for device_index, slots in enumerate(self._gpu_device_slots):
                    semaphore = self._gpu_devices[device_index]
                    if semaphore is None:
                        continue
                    for _ in range(slots):
                        remaining = max(0.0, deadline - time.monotonic())
                        if not semaphore.acquire(timeout=remaining):
                            raise TimeoutError(f"exclusive GPU lease timed out: {lease_id}")
                        acquired_devices.append(device_index)
            except BaseException:
                for device_index in acquired_devices:
                    semaphore = self._gpu_devices[device_index]
                    assert semaphore is not None
                    semaphore.release()
                self._exclusive_gpu_gate.release()
                raise
            if not acquired_devices:
                self._exclusive_gpu_gate.release()
                raise RuntimeError("exclusive GPU trial requested without any admitted GPU device")
            lease = ResourceLease(
                lease_id=lease_id,
                kind="gpu-exclusive",
                started_at=time.time(),
                slots=len(acquired_devices),
                gpu_device_index=acquired_devices[0],
                gpu_device_indices=tuple(acquired_devices),
            )
            with self._lock:
                self._active_gpu_trials += lease.slots
                for device_index in acquired_devices:
                    self._active_gpu_by_device[device_index] += 1
                self._leases.append(lease)
            return lease

        if requires_gpu:
            deadline = time.monotonic() + lease_timeout
            if not self._exclusive_gpu_gate.acquire(timeout=lease_timeout):
                raise TimeoutError(f"GPU admission gate timed out: {lease_id}")
            try:
                device_index = self._acquire_gpu_device(deadline=deadline, lease_id=lease_id)
            finally:
                self._exclusive_gpu_gate.release()
            lease = ResourceLease(
                lease_id=lease_id,
                kind="gpu",
                started_at=time.time(),
                gpu_device_index=device_index,
                gpu_device_indices=(device_index,),
            )
            with self._lock:
                self._leases.append(lease)
            return lease

        ok = self._cpu.acquire(timeout=lease_timeout)
        if not ok:
            raise TimeoutError(f"resource lease timed out: {lease_id}")
        lease = ResourceLease(
            lease_id=lease_id,
            kind="cpu",
            started_at=time.time(),
        )
        with self._lock:
            self._leases.append(lease)
        return lease

    def release(self, lease: ResourceLease) -> None:
        lease.released_at = time.time()
        if lease.kind == "gpu-exclusive":
            with self._lock:
                self._active_gpu_trials = max(0, self._active_gpu_trials - lease.slots)
                for device_index in lease.gpu_device_indices:
                    self._active_gpu_by_device[device_index] = max(
                        0, self._active_gpu_by_device[device_index] - 1
                    )
            for device_index in lease.gpu_device_indices:
                semaphore = self._gpu_devices[device_index]
                assert semaphore is not None
                semaphore.release()
            self._exclusive_gpu_gate.release()
        elif lease.kind == "gpu":
            device_index = lease.gpu_device_index
            if device_index is None:
                raise RuntimeError("GPU lease is missing gpu_device_index")
            with self._lock:
                self._active_gpu_trials = max(0, self._active_gpu_trials - 1)
                self._active_gpu_by_device[device_index] = max(
                    0, self._active_gpu_by_device[device_index] - 1
                )
            semaphore = self._gpu_devices[device_index]
            assert semaphore is not None
            semaphore.release()
        else:
            self._cpu.release()

    def report(self) -> list[dict[str, Any]]:
        with self._lock:
            return [lease.to_dict() for lease in self._leases]

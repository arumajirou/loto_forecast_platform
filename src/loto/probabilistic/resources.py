from __future__ import annotations

import threading
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

GPU_CAPABLE_BACKENDS = frozenset(
    {
        "numpyro",
        "pyro",
        "blackjax",
        "pymc+blackjax",
        "pymc+numpyro",
        "tfp",
        "tensorflow_probability",
    }
)


@dataclass(frozen=True)
class ProbabilisticResourcePolicy:
    outer_workers: int = 8
    max_heavy_cpu_jobs: int = 2
    max_gpu_jobs: int = 1
    gpu_priority: bool = True
    gpu_backends: tuple[str, ...] = tuple(sorted(GPU_CAPABLE_BACKENDS))
    native_device: str = "auto"

    def limit_for(self, resource_class: str) -> int:
        if resource_class == "gpu":
            return self.max_gpu_jobs
        if resource_class == "heavy_cpu":
            return self.max_heavy_cpu_jobs
        return self.outer_workers

    def effective_resource(self, trial: Any) -> str:
        backend = str(getattr(trial, "backend", ""))
        declared = str(getattr(trial, "resource_class", "") or "light_cpu")
        if self.gpu_priority and self.native_device != "cpu" and backend in set(self.gpu_backends):
            return "gpu"
        if declared == "gpu":
            return "gpu"
        if declared == "heavy_cpu":
            return "heavy_cpu"
        return "light_cpu"


class ProbabilisticResourceScheduler:
    """Legacy semaphore scheduler kept for API compatibility."""

    def __init__(self, policy: ProbabilisticResourcePolicy):
        self.policy = policy
        self._light = threading.BoundedSemaphore(policy.outer_workers)
        self._heavy = threading.BoundedSemaphore(policy.max_heavy_cpu_jobs)
        self._gpu = threading.BoundedSemaphore(max(1, policy.max_gpu_jobs))

    @contextmanager
    def lease(self, resource_class: str) -> Iterator[None]:
        if resource_class == "gpu":
            if self.policy.max_gpu_jobs == 0:
                raise RuntimeError("GPU execution requested but max_gpu_jobs=0")
            semaphore = self._gpu
        elif resource_class == "heavy_cpu":
            semaphore = self._heavy
        else:
            semaphore = self._light
        semaphore.acquire()
        try:
            yield
        finally:
            semaphore.release()


class ResourceAwareDispatcher:
    """Submit only runnable trials and optionally prioritize GPU-capable work.

    Pending jobs remain outside the ThreadPool until both a global worker and the
    relevant resource-class capacity are available. This prevents heavy jobs
    waiting on semaphores from occupying all outer workers.
    """

    def __init__(self, policy: ProbabilisticResourcePolicy, trials: list[Any]):
        self.policy = policy
        order = (
            ("gpu", "heavy_cpu", "light_cpu")
            if policy.gpu_priority
            else ("heavy_cpu", "gpu", "light_cpu")
        )
        self.resource_order = order
        self._queues: dict[str, deque[Any]] = {name: deque() for name in order}
        self._running = {name: 0 for name in order}
        self._peak = {name: 0 for name in order}
        self._peak_total = 0
        self._rotation = deque(order)
        self._resource_by_trial_id: dict[str, str] = {}
        for trial in trials:
            resource = policy.effective_resource(trial)
            self._queues[resource].append(trial)
            self._resource_by_trial_id[str(getattr(trial, "trial_id", id(trial)))] = resource

    def resource_for(self, trial: Any) -> str:
        trial_id = str(getattr(trial, "trial_id", id(trial)))
        return self._resource_by_trial_id.get(trial_id, self.policy.effective_resource(trial))

    def pending_count(self) -> int:
        return sum(len(queue) for queue in self._queues.values())

    def running_count(self) -> int:
        return sum(self._running.values())

    def has_work(self) -> bool:
        return bool(self.pending_count() or self.running_count())

    def pop_ready(self) -> Any | None:
        if self.running_count() >= self.policy.outer_workers:
            return None
        for _ in range(len(self._rotation)):
            resource = self._rotation[0]
            self._rotation.rotate(-1)
            if not self._queues[resource]:
                continue
            limit = self.policy.limit_for(resource)
            if limit <= 0 or self._running[resource] >= limit:
                continue
            self._running[resource] += 1
            self._peak[resource] = max(self._peak[resource], self._running[resource])
            self._peak_total = max(self._peak_total, self.running_count())
            return self._queues[resource].popleft()
        return None

    def release(self, trial_or_resource: Any) -> None:
        if isinstance(trial_or_resource, str) and trial_or_resource in self._running:
            resource = trial_or_resource
        else:
            resource = self.resource_for(trial_or_resource)
        if self._running[resource] <= 0:
            raise RuntimeError(f"resource release underflow: {resource}")
        self._running[resource] -= 1

    def running_by_resource(self) -> dict[str, int]:
        return dict(self._running)

    def pending_by_resource(self) -> dict[str, int]:
        return {name: len(queue) for name, queue in self._queues.items()}

    def audit(self) -> dict[str, Any]:
        return {
            "outer_workers": self.policy.outer_workers,
            "gpu_priority": self.policy.gpu_priority,
            "native_device": self.policy.native_device,
            "limits": {
                "gpu": self.policy.max_gpu_jobs,
                "heavy_cpu": self.policy.max_heavy_cpu_jobs,
                "light_cpu": self.policy.outer_workers,
            },
            "running_total": self.running_count(),
            "peak_running_total": self._peak_total,
            "running_by_resource": self.running_by_resource(),
            "peak_running_by_resource": dict(self._peak),
            "pending_by_resource": self.pending_by_resource(),
            "resource_order": list(self.resource_order),
        }


__all__ = [
    "GPU_CAPABLE_BACKENDS",
    "ProbabilisticResourcePolicy",
    "ProbabilisticResourceScheduler",
    "ResourceAwareDispatcher",
]

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from loto.models.catalog_full import ModelEntry
from loto.orchestration.resource_scheduler import ResourcePolicy

# Evidence-backed light-GPU set. These six models completed a six-way concurrent
# Numbers4 smoke on the RTX 5070 Ti profile at source head
# c403dbd0e10e9ef2ff514fc142108ff3fa428ebf. Do not broaden this set without
# measured evidence; unmeasured NeuralForecast models remain MEDIUM by default.
VERIFIED_GPU_LIGHT_MODEL_IDS = frozenset(
    {
        "nfauto-rnn",
        "nfauto-lstm",
        "nfauto-gru",
        "nfauto-tcn",
        "nfauto-deepar",
        "nfauto-dilatedrnn",
    }
)


@dataclass(frozen=True)
class WeightedGpuProfile:
    name: str
    slots: int | None
    reason: str

    @property
    def requires_gpu(self) -> bool:
        return self.name != "CPU"

    @property
    def exclusive(self) -> bool:
        return self.name == "EXCLUSIVE_GPU"

    def resolve_slots(self, capacity_slots: int) -> int:
        if not self.requires_gpu:
            return 0
        if capacity_slots < 1:
            raise ValueError("capacity_slots must be >= 1 for a GPU profile")
        if self.exclusive:
            return capacity_slots
        requested = int(self.slots or 1)
        return min(capacity_slots, max(1, requested))

    def to_dict(self, *, capacity_slots: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "configured_slots": self.slots,
            "reason": self.reason,
        }
        if capacity_slots is not None and self.requires_gpu:
            payload["resolved_slots"] = self.resolve_slots(capacity_slots)
        return payload


CPU_PROFILE = WeightedGpuProfile("CPU", 0, "CPU-only execution path")
GPU_LIGHT_PROFILE = WeightedGpuProfile(
    "GPU_LIGHT",
    1,
    "measured light-GPU profile; one base VRAM slot",
)
GPU_MEDIUM_PROFILE = WeightedGpuProfile(
    "GPU_MEDIUM",
    2,
    "unmeasured or broader NeuralForecast profile; two base VRAM slots",
)
GPU_HEAVY_PROFILE = WeightedGpuProfile(
    "GPU_HEAVY",
    3,
    "GPU-capable model without light-profile evidence; three base VRAM slots",
)
EXCLUSIVE_GPU_PROFILE = WeightedGpuProfile(
    "EXCLUSIVE_GPU",
    None,
    "foundation/heavy profile; reserve all resolved GPU slots",
)


def profile_for_metadata(
    *,
    model_id: str,
    library: str,
    class_name: str = "",
    capabilities: tuple[str, ...] = (),
) -> WeightedGpuProfile:
    """Return a conservative weighted GPU profile from catalog metadata.

    The policy is evidence-first. Only models with an explicit concurrency smoke are
    LIGHT. Other NeuralForecast models are MEDIUM. Foundation/zero-shot TSFM entries
    and TimeLLM are exclusive until independently profiled. Unknown GPU-capable
    entries are HEAVY rather than optimistically classified as LIGHT.
    """

    normalized = model_id.lower()
    capability_set = {item.lower() for item in capabilities}

    if normalized == "nf-timellm" or class_name == "TimeLLM":
        return EXCLUSIVE_GPU_PROFILE
    if library == "tsfm" or "zero_shot" in capability_set or "foundation" in capability_set:
        return EXCLUSIVE_GPU_PROFILE
    if normalized in VERIFIED_GPU_LIGHT_MODEL_IDS:
        return GPU_LIGHT_PROFILE
    if library in {"neuralforecast", "neuralforecast_auto"}:
        return GPU_MEDIUM_PROFILE
    if "gpu" in capability_set or "gpu_optional" in capability_set:
        return GPU_HEAVY_PROFILE
    return CPU_PROFILE


def profile_for_entry(entry: ModelEntry) -> WeightedGpuProfile:
    return profile_for_metadata(
        model_id=entry.model_id,
        library=entry.library,
        class_name=entry.class_name,
        capabilities=entry.capabilities,
    )


def weighted_runtime_resource_class(
    *,
    model_id: str,
    library: str,
    class_name: str = "",
    capabilities: tuple[str, ...] = (),
) -> str:
    """Compatibility classifier for the existing broad runner.

    The existing runner understands CPU, GPU, and EXCLUSIVE_GPU. Weighted slot detail
    is carried by :class:`WeightedResourceScheduler` and persisted in each lease.
    """

    profile = profile_for_metadata(
        model_id=model_id,
        library=library,
        class_name=class_name,
        capabilities=capabilities,
    )
    if not profile.requires_gpu:
        return "CPU"
    return "EXCLUSIVE_GPU" if profile.exclusive else "GPU"


_PROFILE_BY_MODEL_ID: dict[str, WeightedGpuProfile] = {}


def configure_weighted_profiles(entries: Iterable[ModelEntry]) -> dict[str, WeightedGpuProfile]:
    global _PROFILE_BY_MODEL_ID
    _PROFILE_BY_MODEL_ID = {entry.model_id: profile_for_entry(entry) for entry in entries}
    return dict(_PROFILE_BY_MODEL_ID)


def profile_for_model_id(model_id: str) -> WeightedGpuProfile:
    profile = _PROFILE_BY_MODEL_ID.get(model_id)
    if profile is not None:
        return profile
    # An unregistered GPU task must never silently receive a LIGHT reservation.
    return GPU_HEAVY_PROFILE


@dataclass
class WeightedResourceLease:
    lease_id: str
    kind: str
    resource_profile: str
    started_at: float
    slots: int = 1
    scheduler_pid: int = field(default_factory=os.getpid)
    child_pid: int | None = None
    released_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "kind": self.kind,
            # Keep pid for backward compatibility, but name its meaning explicitly.
            "pid": self.scheduler_pid,
            "scheduler_pid": self.scheduler_pid,
            "child_pid": self.child_pid,
            "resource_profile": self.resource_profile,
            "started_at": self.started_at,
            "released_at": self.released_at,
            "slots": self.slots,
        }


class WeightedResourceScheduler:
    """Slot-weighted CPU/GPU admission controller.

    ``max_parallel_gpu_models`` from ``ResourcePolicy`` is treated as the number of
    resolved *base GPU slots*. With a 2 GiB base slot on the tested 16 GiB GPU, the
    current resource plan resolves six safe slots after the configured safety margin.
    LIGHT/MEDIUM/HEAVY jobs consume 1/2/3 slots respectively; EXCLUSIVE consumes all.
    """

    def __init__(self, policy: ResourcePolicy):
        if policy.max_parallel_cpu_models < 1:
            raise ValueError("max_parallel_cpu_models must be >= 1")
        if policy.max_parallel_gpu_models < 0:
            raise ValueError("max_parallel_gpu_models must be >= 0")
        self.policy = policy
        self._cpu = threading.BoundedSemaphore(policy.max_parallel_cpu_models)
        self._gpu = threading.BoundedSemaphore(max(1, policy.max_parallel_gpu_models))
        self._exclusive_gpu_gate = threading.Lock()
        self._lock = threading.Lock()
        self._leases: list[WeightedResourceLease] = []
        self._active_gpu_slots = 0
        self._active_gpu_leases = 0

    @property
    def gpu_capacity_slots(self) -> int:
        return self.policy.max_parallel_gpu_models

    def _profile_for_lease(self, lease_id: str, *, exclusive_gpu: bool) -> WeightedGpuProfile:
        if exclusive_gpu:
            return EXCLUSIVE_GPU_PROFILE
        model_id = lease_id.split("::", maxsplit=1)[0]
        return profile_for_model_id(model_id)

    def gpu_resource_status(
        self,
        *,
        estimated_vram_mib: int | None = None,
        requested_slots: int = 1,
    ) -> dict[str, Any]:
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
            active_gpu_slots = self._active_gpu_slots
            active_gpu_leases = self._active_gpu_leases
        enough_slots = active_gpu_slots + requested_slots <= self.gpu_capacity_slots
        enough_vram = (
            free_vram_mib is None
            or estimated is None
            or free_vram_mib - self.policy.gpu_memory_safety_margin_mib
            >= estimated * requested_slots
        )
        return {
            "free_vram_mib": free_vram_mib,
            "base_slot_vram_mib": estimated,
            "running_gpu_leases": active_gpu_leases,
            "running_gpu_slots": active_gpu_slots,
            "gpu_capacity_slots": self.gpu_capacity_slots,
            "requested_slots": requested_slots,
            "safety_margin_mib": self.policy.gpu_memory_safety_margin_mib,
            "decision": "AVAILABLE" if enough_slots and enough_vram else "WAITING_FOR_GPU_RESOURCE",
        }

    def _acquire_gpu_slots(self, slots: int, *, deadline: float, lease_id: str) -> None:
        acquired = 0
        try:
            for _ in range(slots):
                remaining = max(0.0, deadline - time.monotonic())
                if not self._gpu.acquire(timeout=remaining):
                    raise TimeoutError(
                        f"GPU slot lease timed out: {lease_id}; requested_slots={slots}"
                    )
                acquired += 1
        except BaseException:
            for _ in range(acquired):
                self._gpu.release()
            raise

    def acquire(
        self,
        *,
        requires_gpu: bool,
        lease_id: str,
        timeout: float | None = None,
        exclusive_gpu: bool = False,
    ) -> WeightedResourceLease:
        lease_timeout = timeout if timeout is not None else self.policy.timeout_seconds
        if requires_gpu and self.gpu_capacity_slots == 0:
            raise RuntimeError("GPU trial requested but GPU capacity slots are 0")

        if not requires_gpu:
            if not self._cpu.acquire(timeout=lease_timeout):
                raise TimeoutError(f"CPU resource lease timed out: {lease_id}")
            lease = WeightedResourceLease(
                lease_id=lease_id,
                kind="cpu",
                resource_profile="CPU",
                started_at=time.time(),
                slots=1,
            )
            with self._lock:
                self._leases.append(lease)
            return lease

        profile = self._profile_for_lease(lease_id, exclusive_gpu=exclusive_gpu)
        slots = profile.resolve_slots(self.gpu_capacity_slots)
        deadline = time.monotonic() + lease_timeout

        if not self._exclusive_gpu_gate.acquire(timeout=lease_timeout):
            raise TimeoutError(f"GPU admission gate timed out: {lease_id}")
        keep_gate_until_release = profile.exclusive
        try:
            self._acquire_gpu_slots(slots, deadline=deadline, lease_id=lease_id)
        except BaseException:
            self._exclusive_gpu_gate.release()
            raise
        if not keep_gate_until_release:
            self._exclusive_gpu_gate.release()

        lease = WeightedResourceLease(
            lease_id=lease_id,
            kind="gpu-exclusive" if profile.exclusive else "gpu",
            resource_profile=profile.name,
            started_at=time.time(),
            slots=slots,
        )
        with self._lock:
            self._active_gpu_slots += slots
            self._active_gpu_leases += 1
            self._leases.append(lease)
        return lease

    def release(self, lease: WeightedResourceLease) -> None:
        lease.released_at = time.time()
        if lease.kind == "cpu":
            self._cpu.release()
            return

        with self._lock:
            self._active_gpu_slots = max(0, self._active_gpu_slots - lease.slots)
            self._active_gpu_leases = max(0, self._active_gpu_leases - 1)
        for _ in range(lease.slots):
            self._gpu.release()
        if lease.kind == "gpu-exclusive":
            self._exclusive_gpu_gate.release()

    def report(self) -> list[dict[str, Any]]:
        with self._lock:
            return [lease.to_dict() for lease in self._leases]

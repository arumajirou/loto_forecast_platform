from __future__ import annotations

import threading
import time

from loto.orchestration.resource_scheduler import (
    ResourcePolicy,
    ResourceScheduler,
    ResourceSnapshot,
    resolve_resource_plan,
    runtime_resource_class,
)


def test_resolve_resource_plan_uses_cpu_ram_and_vram_capacity() -> None:
    snapshot = ResourceSnapshot(
        logical_cpus=32,
        available_ram_mib=65536,
        gpu_count=1,
        gpu_total_mib=(16303,),
        gpu_free_mib=(15000,),
    )

    plan = resolve_resource_plan(
        snapshot,
        outer_worker_cap=8,
        cpus_per_trial=2,
        ram_per_cpu_job_mib=6144,
        gpu_slot_mib=5120,
        safety_margin_mib=2048,
    )

    assert plan.parallel_gpu_models == 2
    assert plan.parallel_cpu_models == 6
    assert plan.parallel_exclusive_gpu_models == 1
    assert plan.parallel_cpu_models + plan.parallel_gpu_models <= 8


def test_timellm_is_exclusive_gpu_resource_class() -> None:
    assert (
        runtime_resource_class(
            model_id="nf-timellm",
            library="neuralforecast",
            class_name="TimeLLM",
        )
        == "EXCLUSIVE_GPU"
    )
    assert (
        runtime_resource_class(
            model_id="nf-dlinear",
            library="neuralforecast",
            class_name="DLinear",
        )
        == "GPU"
    )
    assert (
        runtime_resource_class(
            model_id="sf-autoarima",
            library="statsforecast",
            class_name="AutoARIMA",
        )
        == "CPU"
    )


def test_exclusive_gpu_lease_waits_for_regular_gpu_lease() -> None:
    scheduler = ResourceScheduler(
        ResourcePolicy(
            max_parallel_cpu_models=2,
            max_parallel_gpu_models=2,
            timeout_seconds=2,
        )
    )
    regular = scheduler.acquire(requires_gpu=True, lease_id="regular")
    acquired = threading.Event()
    released = threading.Event()

    def worker() -> None:
        lease = scheduler.acquire(
            requires_gpu=True,
            lease_id="exclusive",
            exclusive_gpu=True,
            timeout=1.5,
        )
        acquired.set()
        scheduler.release(lease)
        released.set()

    thread = threading.Thread(target=worker)
    thread.start()
    time.sleep(0.05)
    assert not acquired.is_set()

    scheduler.release(regular)
    thread.join(timeout=2)

    assert acquired.is_set()
    assert released.is_set()

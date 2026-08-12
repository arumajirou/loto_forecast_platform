from __future__ import annotations

from loto.orchestration.resource_scheduler import (
    ResourcePolicy,
    ResourceScheduler,
    ResourceSnapshot,
    resolve_resource_plan,
)


def test_multi_gpu_plan_preserves_physical_device_slots() -> None:
    snapshot = ResourceSnapshot(
        logical_cpus=32,
        available_ram_mib=65536,
        gpu_count=2,
        gpu_total_mib=(16303, 16303),
        gpu_free_mib=(9000, 9000),
    )

    plan = resolve_resource_plan(
        snapshot,
        outer_worker_cap=3,
        cpus_per_trial=2,
        ram_per_cpu_job_mib=6144,
        gpu_slot_mib=5120,
        safety_margin_mib=2048,
    )

    assert plan.parallel_cpu_models == 1
    assert plan.parallel_gpu_models == 2
    assert plan.gpu_device_slots == (1, 1)
    assert plan.executor_mode == "shared_outer_pool"


def test_multi_gpu_regular_leases_map_to_different_physical_devices() -> None:
    scheduler = ResourceScheduler(
        ResourcePolicy(
            max_parallel_cpu_models=1,
            max_parallel_gpu_models=2,
            gpu_device_slots=(1, 1),
            timeout_seconds=1,
        )
    )

    first = scheduler.acquire(requires_gpu=True, lease_id="first")
    second = scheduler.acquire(requires_gpu=True, lease_id="second")
    try:
        assert {first.gpu_device_index, second.gpu_device_index} == {0, 1}
        assert first.gpu_device_indices == (first.gpu_device_index,)
        assert second.gpu_device_indices == (second.gpu_device_index,)
    finally:
        scheduler.release(first)
        scheduler.release(second)


def test_outer_cap_one_keeps_both_lanes_routable_under_shared_pool() -> None:
    snapshot = ResourceSnapshot(
        logical_cpus=32,
        available_ram_mib=65536,
        gpu_count=1,
        gpu_total_mib=(16303,),
        gpu_free_mib=(15000,),
    )

    plan = resolve_resource_plan(
        snapshot,
        outer_worker_cap=1,
        cpus_per_trial=2,
        ram_per_cpu_job_mib=6144,
        gpu_slot_mib=5120,
        safety_margin_mib=2048,
    )

    assert plan.parallel_cpu_models == 1
    assert plan.parallel_gpu_models == 1
    assert plan.outer_worker_cap == 1
    assert plan.executor_mode == "shared_outer_pool"

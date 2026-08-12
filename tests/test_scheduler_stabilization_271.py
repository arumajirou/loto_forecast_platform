from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from loto.orchestration.resource_aware_broad_campaign_impl import _run_process
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


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group cleanup smoke")
def test_timeout_smoke_removes_descendant_process_tree(tmp_path: Path) -> None:
    child_pid_path = tmp_path / "child.pid"
    parent_code = "\n".join(
        [
            "import subprocess",
            "import sys",
            "import time",
            "from pathlib import Path",
            'child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])',
            'Path(sys.argv[1]).write_text(str(child.pid), encoding="utf-8")',
            "time.sleep(60)",
        ]
    )

    rc, _, _, timed_out, termination = _run_process(
        [sys.executable, "-c", parent_code, str(child_pid_path)],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout_seconds=1,
    )

    assert rc is None
    assert timed_out is True
    assert termination["method"] == "posix-process-group"
    assert termination["tree_cleanup_complete"] is True
    assert child_pid_path.exists()

    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    child_proc = Path(f"/proc/{child_pid}")
    deadline = time.monotonic() + 5.0
    while child_proc.exists() and time.monotonic() < deadline:
        time.sleep(0.05)

    assert not child_proc.exists(), f"orphan child still exists after timeout: pid={child_pid}"

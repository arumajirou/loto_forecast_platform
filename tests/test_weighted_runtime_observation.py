from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from loto.orchestration.resource_scheduler import ResourcePolicy


def _load_weighted_runner_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_weighted_resource_aware_broad_campaign.py"
    )
    spec = importlib.util.spec_from_file_location("weighted_observed_runner", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_observed_scheduler_binds_real_child_pid_and_process_evidence(tmp_path) -> None:
    module = _load_weighted_runner_module()
    scheduler = module.ObservedWeightedResourceScheduler(
        ResourcePolicy(
            max_parallel_cpu_models=1,
            max_parallel_gpu_models=1,
            max_vram_mib=2048,
            timeout_seconds=5,
        )
    )
    lease = scheduler.acquire(
        requires_gpu=False,
        lease_id="sf-autoarima::numbers4",
        timeout=2,
    )
    runtime_workdir = tmp_path / "attempt" / "runtime-workdir"
    runtime_workdir.mkdir(parents=True)

    proxy = module._SubprocessProxy()
    completed = proxy.run(
        [sys.executable, "-c", "print('observed')"],
        cwd=runtime_workdir,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    scheduler.release(lease)

    assert completed.returncode == 0
    assert completed.stdout.strip() == "observed"
    assert lease.child_pid is not None
    assert lease.child_pid > 0

    evidence_path = runtime_workdir.parent / "PROCESS_OBSERVATION.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["child_pid"] == lease.child_pid
    assert any(node["pid"] == lease.child_pid for node in evidence["process_tree"])
    assert evidence["sample_count"] >= 1
    assert scheduler.report()[0]["child_pid"] == lease.child_pid


def test_device_evidence_does_not_claim_fallback_without_attributed_gpu_pid() -> None:
    module = _load_weighted_runner_module()

    unresolved = module._device_evidence(
        resource_class="GPU",
        observation={"gpu_pids": [], "gpu_attribution_available": True},
    )
    attributed = module._device_evidence(
        resource_class="GPU",
        observation={"gpu_pids": [1234], "gpu_attribution_available": True},
    )
    cpu = module._device_evidence(
        resource_class="CPU",
        observation={"gpu_pids": [], "gpu_attribution_available": False},
    )

    assert unresolved["cpu_fallback_status"] == "UNRESOLVED_NO_MATCHED_GPU_PID"
    assert attributed["cpu_fallback_status"] == "NOT_OBSERVED_GPU_PID_ATTRIBUTED"
    assert cpu["cpu_fallback_status"] == "NOT_APPLICABLE_CPU_CONTRACT"

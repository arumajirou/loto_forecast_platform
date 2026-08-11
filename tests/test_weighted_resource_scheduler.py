from __future__ import annotations

import importlib.util
import sys
import threading
import time
from pathlib import Path

from loto.models.catalog_full import build_catalog
from loto.orchestration.resource_scheduler import ResourcePolicy
from loto.orchestration.weighted_resource_scheduler import (
    EXCLUSIVE_GPU_PROFILE,
    GPU_HEAVY_PROFILE,
    GPU_LIGHT_PROFILE,
    GPU_MEDIUM_PROFILE,
    WeightedResourceScheduler,
    configure_weighted_profiles,
    profile_for_entry,
    profile_for_metadata,
)


def _entry(model_id: str):
    return next(entry for entry in build_catalog() if entry.model_id == model_id)


def test_evidence_backed_light_profiles_and_conservative_defaults() -> None:
    for model_id in (
        "nfauto-rnn",
        "nfauto-lstm",
        "nfauto-gru",
        "nfauto-tcn",
        "nfauto-deepar",
        "nfauto-dilatedrnn",
    ):
        assert profile_for_entry(_entry(model_id)) == GPU_LIGHT_PROFILE

    assert profile_for_entry(_entry("nf-dlinear")) == GPU_MEDIUM_PROFILE
    assert profile_for_entry(_entry("nf-timellm")) == EXCLUSIVE_GPU_PROFILE
    assert (
        profile_for_metadata(
            model_id="custom-gpu-model",
            library="custom",
            capabilities=("gpu",),
        )
        == GPU_HEAVY_PROFILE
    )


def test_light_jobs_can_fill_six_base_gpu_slots() -> None:
    configure_weighted_profiles(build_catalog())
    scheduler = WeightedResourceScheduler(
        ResourcePolicy(
            max_parallel_cpu_models=2,
            max_parallel_gpu_models=6,
            max_vram_mib=2048,
            timeout_seconds=1,
        )
    )

    model_ids = (
        "nfauto-rnn",
        "nfauto-lstm",
        "nfauto-gru",
        "nfauto-tcn",
        "nfauto-deepar",
        "nfauto-dilatedrnn",
    )
    leases = [
        scheduler.acquire(
            requires_gpu=True,
            lease_id=f"{model_id}::numbers4",
            timeout=0.5,
        )
        for model_id in model_ids
    ]

    assert [lease.slots for lease in leases] == [1] * 6
    assert {lease.resource_profile for lease in leases} == {"GPU_LIGHT"}

    for lease in leases:
        scheduler.release(lease)

    assert all(row["released_at"] is not None for row in scheduler.report())


def test_medium_jobs_consume_two_slots_each() -> None:
    configure_weighted_profiles(build_catalog())
    scheduler = WeightedResourceScheduler(
        ResourcePolicy(
            max_parallel_cpu_models=2,
            max_parallel_gpu_models=6,
            max_vram_mib=2048,
            timeout_seconds=1,
        )
    )

    leases = [
        scheduler.acquire(
            requires_gpu=True,
            lease_id="nf-dlinear::numbers4",
            timeout=0.5,
        )
        for _ in range(3)
    ]

    assert [lease.slots for lease in leases] == [2, 2, 2]
    assert {lease.resource_profile for lease in leases} == {"GPU_MEDIUM"}

    for lease in leases:
        scheduler.release(lease)


def test_exclusive_job_waits_until_all_weighted_slots_are_free() -> None:
    configure_weighted_profiles(build_catalog())
    scheduler = WeightedResourceScheduler(
        ResourcePolicy(
            max_parallel_cpu_models=2,
            max_parallel_gpu_models=6,
            max_vram_mib=2048,
            timeout_seconds=2,
        )
    )

    regular = scheduler.acquire(
        requires_gpu=True,
        lease_id="nfauto-rnn::numbers4",
        timeout=0.5,
    )
    acquired = threading.Event()
    holder: list[object] = []

    def worker() -> None:
        lease = scheduler.acquire(
            requires_gpu=True,
            lease_id="nf-timellm::numbers4",
            exclusive_gpu=True,
            timeout=1.5,
        )
        holder.append(lease)
        acquired.set()

    thread = threading.Thread(target=worker)
    thread.start()
    time.sleep(0.05)
    assert not acquired.is_set()

    scheduler.release(regular)
    assert acquired.wait(timeout=1.0)

    exclusive = holder[0]
    assert exclusive.slots == 6
    assert exclusive.resource_profile == "EXCLUSIVE_GPU"
    scheduler.release(exclusive)
    thread.join(timeout=1.0)


def _load_weighted_runner_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_weighted_resource_aware_broad_campaign.py"
    )
    spec = importlib.util.spec_from_file_location("weighted_resource_runner", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_weighted_runner_injects_two_gib_base_slot_only_when_unspecified() -> None:
    module = _load_weighted_runner_module()

    assert module._inject_weighted_defaults(["--models", "all"])[-2:] == [
        "--gpu-slot-mib",
        "2048",
    ]
    explicit = ["--models", "all", "--gpu-slot-mib", "4096"]
    assert module._inject_weighted_defaults(explicit) == explicit

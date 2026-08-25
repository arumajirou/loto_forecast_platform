from __future__ import annotations

from loto.gpu_exclusive.adapters import (
    GpuProcessSnapshot,
    GpuSnapshot,
    RuntimeIdentitySnapshot,
)
from loto.gpu_exclusive.models import (
    GpuResidencyPolicy,
    GpuResidencyProfile,
    ResidencyProfileSelector,
)
from loto.gpu_exclusive.residency import decide_residency


def _gpu(*, free: int = 5000) -> GpuSnapshot:
    return GpuSnapshot(
        index=0,
        uuid="GPU-test",
        memory_used_mib=16303 - free,
        memory_free_mib=free,
        memory_total_mib=16303,
    )


def _selector() -> ResidencyProfileSelector:
    return ResidencyProfileSelector(
        llm_alias="qwen38-27b-ud-iq3xxs-mtp3",
        llm_runtime="ik_llama",
        llm_context_length=65536,
        foundation_repo_id="Salesforce/moirai-2.0-R-small",
        foundation_revision="30f43ff08c8494f4943ae1521e9d4e94a0fbb389",
        runtime_lane="cuda13-experimental",
    )


def _policy(mode: str = "auto") -> GpuResidencyPolicy:
    return GpuResidencyPolicy(
        mode=mode,
        profile_selector=_selector(),
        hard_reserve_mib=2048,
        reserve_ratio=0.0,
        foundation_peak_safety_factor=1.25,
        minimum_foundation_budget_mib=1024,
    )


def _profile(*, certified: bool = True, peak: int | None = 2000) -> GpuResidencyProfile:
    return GpuResidencyProfile.model_validate(
        {
            "profile_id": "profile-1",
            "certified": certified,
            "gpu": {"uuid": "GPU-test", "index": 0},
            "llm": {
                "alias": "qwen38-27b-ud-iq3xxs-mtp3",
                "runtime": "ik_llama",
                "context_length": 65536,
                "process_names": ["llama-server"],
            },
            "foundation": {
                "repo_id": "Salesforce/moirai-2.0-R-small",
                "revision": "30f43ff08c8494f4943ae1521e9d4e94a0fbb389",
                "runtime_lane": "cuda13-experimental",
            },
            "evidence": {
                "external_peak_vram_mib": peak,
                "sample_count": 3 if peak else 0,
                "certification_run_ids": ["r1", "r2", "r3"] if peak else [],
            },
        }
    )


def _runtime(body: str = "qwen38-27b-ud-iq3xxs-mtp3") -> RuntimeIdentitySnapshot:
    return RuntimeIdentitySnapshot(running=True, body=body, body_sha256="x")


def _processes(*, foreign: bool = False) -> list[GpuProcessSnapshot]:
    rows = [
        GpuProcessSnapshot(
            gpu_uuid="GPU-test",
            pid=100,
            process_name="llama-server",
            used_memory_mib=12000,
        )
    ]
    if foreign:
        rows.append(
            GpuProcessSnapshot(
                gpu_uuid="GPU-test",
                pid=200,
                process_name="other",
                used_memory_mib=200,
            )
        )
    return rows


def test_auto_unknown_profile_falls_back_to_handoff() -> None:
    decision = decide_residency(
        _policy(),
        gpu=_gpu(),
        processes=_processes(),
        runtime=_runtime(),
        profile=None,
    )
    assert decision.selected_mode == "handoff"
    assert decision.fallback_triggered is True


def test_auto_enough_vram_selects_coexist() -> None:
    decision = decide_residency(
        _policy(),
        gpu=_gpu(free=4548),
        processes=_processes(),
        runtime=_runtime(),
        profile=_profile(),
    )
    assert decision.selected_mode == "coexist"
    assert decision.foundation_budget_mib == 2500
    assert decision.safety_reserve_mib == 2048


def test_exact_threshold_selects_coexist() -> None:
    decision = decide_residency(
        _policy(),
        gpu=_gpu(free=4548),
        processes=_processes(),
        runtime=_runtime(),
        profile=_profile(),
    )
    assert decision.selected_mode == "coexist"


def test_one_mib_short_falls_back_to_handoff() -> None:
    decision = decide_residency(
        _policy(),
        gpu=_gpu(free=4547),
        processes=_processes(),
        runtime=_runtime(),
        profile=_profile(),
    )
    assert decision.selected_mode == "handoff"


def test_forced_coexist_without_headroom_blocks() -> None:
    decision = decide_residency(
        _policy("coexist"),
        gpu=_gpu(free=4547),
        processes=_processes(),
        runtime=_runtime(),
        profile=_profile(),
    )
    assert decision.selected_mode == "block"


def test_forced_handoff_stays_handoff() -> None:
    decision = decide_residency(
        _policy("handoff"),
        gpu=_gpu(),
        processes=_processes(),
        runtime=_runtime(),
        profile=None,
    )
    assert decision.selected_mode == "handoff"


def test_exact_llm_identity_mismatch_blocks() -> None:
    decision = decide_residency(
        _policy(),
        gpu=_gpu(),
        processes=_processes(),
        runtime=_runtime("different-model"),
        profile=_profile(),
    )
    assert decision.selected_mode == "block"
    assert decision.decision_reason == "exact_llm_identity_mismatch"


def test_foreign_gpu_process_forces_auto_handoff() -> None:
    decision = decide_residency(
        _policy(),
        gpu=_gpu(),
        processes=_processes(foreign=True),
        runtime=_runtime(),
        profile=_profile(),
    )
    assert decision.selected_mode == "handoff"
    assert decision.foreign_gpu_pids_before == [200]


def test_uncertified_profile_falls_back_to_handoff() -> None:
    decision = decide_residency(
        _policy(),
        gpu=_gpu(),
        processes=_processes(),
        runtime=_runtime(),
        profile=_profile(certified=False),
    )
    assert decision.selected_mode == "handoff"


def test_missing_external_peak_evidence_falls_back_to_handoff() -> None:
    decision = decide_residency(
        _policy(),
        gpu=_gpu(),
        processes=_processes(),
        runtime=_runtime(),
        profile=_profile(peak=None),
    )
    assert decision.selected_mode == "handoff"

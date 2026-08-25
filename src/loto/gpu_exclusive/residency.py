"""Pure Adaptive GPU Residency profile selection and decision logic."""

from __future__ import annotations

import math
from pathlib import Path

from pydantic import ValidationError

from .adapters import GpuProcessSnapshot, GpuSnapshot, RuntimeIdentitySnapshot
from .models import (
    GpuResidencyPolicy,
    GpuResidencyProfile,
    GpuResidencyProfileRegistry,
    ResidencyDecision,
    ResidencyProfileSelector,
)


class ResidencyProfileError(RuntimeError):
    """Raised when a resource profile registry is malformed."""


def load_profile_registry(path: Path) -> GpuResidencyProfileRegistry:
    try:
        return GpuResidencyProfileRegistry.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise ResidencyProfileError(f"invalid residency profile registry {path}: {exc}") from exc


def select_exact_profile(
    registry: GpuResidencyProfileRegistry,
    *,
    selector: ResidencyProfileSelector,
    gpu: GpuSnapshot,
) -> GpuResidencyProfile | None:
    matches = [
        profile
        for profile in registry.profiles
        if profile.gpu.uuid == gpu.uuid
        and profile.gpu.index == gpu.index
        and profile.llm.alias == selector.llm_alias
        and profile.llm.runtime == selector.llm_runtime
        and profile.llm.context_length == selector.llm_context_length
        and profile.foundation.repo_id == selector.foundation_repo_id
        and profile.foundation.revision == selector.foundation_revision
        and profile.foundation.runtime_lane == selector.runtime_lane
    ]
    if len(matches) > 1:
        raise ResidencyProfileError("multiple exact residency profiles match the same tuple")
    return matches[0] if matches else None


def _fallback(
    policy: GpuResidencyPolicy,
    *,
    reason: str,
    requested_mode: str,
    gpu: GpuSnapshot,
) -> ResidencyDecision:
    if requested_mode == "coexist" or policy.unknown_profile_action == "block":
        selected = "block"
        fallback = False
    else:
        selected = "handoff"
        fallback = True
    return ResidencyDecision(
        requested_mode=requested_mode,  # type: ignore[arg-type]
        selected_mode=selected,  # type: ignore[arg-type]
        decision_reason=reason,
        gpu_uuid=gpu.uuid,
        gpu_total_mib=gpu.memory_total_mib,
        gpu_used_before_mib=gpu.memory_used_mib,
        gpu_free_before_mib=gpu.memory_free_mib,
        fallback_triggered=fallback,
    )


def decide_residency(
    policy: GpuResidencyPolicy,
    *,
    gpu: GpuSnapshot,
    processes: list[GpuProcessSnapshot],
    runtime: RuntimeIdentitySnapshot,
    profile: GpuResidencyProfile | None,
) -> ResidencyDecision:
    """Return a deterministic COEXIST/HANDOFF/BLOCK decision without side effects."""

    requested = policy.mode
    if requested == "handoff":
        return ResidencyDecision(
            requested_mode="handoff",
            selected_mode="handoff",
            decision_reason="operator_forced_handoff",
            gpu_uuid=gpu.uuid,
            gpu_total_mib=gpu.memory_total_mib,
            gpu_used_before_mib=gpu.memory_used_mib,
            gpu_free_before_mib=gpu.memory_free_mib,
        )

    if profile is None:
        return _fallback(
            policy,
            reason="exact_certified_profile_unavailable",
            requested_mode=requested,
            gpu=gpu,
        )

    evidence = profile.evidence
    if not profile.certified:
        return _fallback(
            policy,
            reason="profile_not_certified",
            requested_mode=requested,
            gpu=gpu,
        )
    if policy.require_external_peak_evidence and (
        evidence.external_peak_vram_mib is None
        or evidence.sample_count <= 0
        or not evidence.certification_run_ids
    ):
        return _fallback(
            policy,
            reason="external_peak_evidence_missing",
            requested_mode=requested,
            gpu=gpu,
        )

    if policy.require_exact_llm_identity and (
        not runtime.running or profile.llm.alias not in runtime.body
    ):
        return ResidencyDecision(
            requested_mode=requested,  # type: ignore[arg-type]
            selected_mode="block",
            decision_reason="exact_llm_identity_mismatch",
            profile_id=profile.profile_id,
            gpu_uuid=gpu.uuid,
            gpu_total_mib=gpu.memory_total_mib,
            gpu_used_before_mib=gpu.memory_used_mib,
            gpu_free_before_mib=gpu.memory_free_mib,
        )

    allowed_names = set(profile.llm.process_names)
    llm_processes = [process for process in processes if process.process_name in allowed_names]
    foreign_processes = [
        process for process in processes if process.process_name not in allowed_names
    ]

    if policy.require_llm_pid_stability_when_available and not llm_processes:
        return _fallback(
            policy,
            reason="llm_gpu_process_not_observed",
            requested_mode=requested,
            gpu=gpu,
        )

    if foreign_processes:
        decision = _fallback(
            policy,
            reason="foreign_gpu_process_present",
            requested_mode=requested,
            gpu=gpu,
        )
        return decision.model_copy(
            update={
                "profile_id": profile.profile_id,
                "llm_gpu_pids_before": sorted(process.pid for process in llm_processes),
                "foreign_gpu_pids_before": sorted(process.pid for process in foreign_processes),
            }
        )

    peak = evidence.external_peak_vram_mib or 0
    reserve = max(policy.hard_reserve_mib, math.ceil(gpu.memory_total_mib * policy.reserve_ratio))
    budget = max(
        policy.minimum_foundation_budget_mib,
        math.ceil(peak * policy.foundation_peak_safety_factor),
    )
    enough = gpu.memory_free_mib >= budget + reserve

    if not enough:
        decision = _fallback(
            policy,
            reason="insufficient_certified_headroom",
            requested_mode=requested,
            gpu=gpu,
        )
        return decision.model_copy(
            update={
                "profile_id": profile.profile_id,
                "foundation_peak_mib": peak,
                "foundation_budget_mib": budget,
                "safety_reserve_mib": reserve,
                "llm_gpu_pids_before": sorted(process.pid for process in llm_processes),
            }
        )

    return ResidencyDecision(
        requested_mode=requested,  # type: ignore[arg-type]
        selected_mode="coexist",
        decision_reason="certified_headroom_available",
        profile_id=profile.profile_id,
        gpu_uuid=gpu.uuid,
        gpu_total_mib=gpu.memory_total_mib,
        gpu_used_before_mib=gpu.memory_used_mib,
        gpu_free_before_mib=gpu.memory_free_mib,
        foundation_peak_mib=peak,
        foundation_budget_mib=budget,
        safety_reserve_mib=reserve,
        llm_gpu_pids_before=sorted(process.pid for process in llm_processes),
        foreign_gpu_pids_before=[],
        fallback_triggered=False,
    )

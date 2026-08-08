from __future__ import annotations

import time
from types import ModuleType
from typing import Any

from loto.orchestration.formal_backtest_ledger import FormalBacktestLedgerRecorder


def run_instrumented_fold(
    *,
    module: ModuleType,
    recorder: FormalBacktestLedgerRecorder,
    model_id: str,
    fold_id: str,
    spec: Any,
    train_df: Any,
    test_row: Any,
    full_df: Any,
    test_idx: int,
    seed: int,
    device: str,
    precision: str,
    stage: str,
) -> tuple[Any, Any, dict[str, Any], float, float, dict[str, Any], dict[str, Any]]:
    params = module.resolve_model_params(spec, stage)
    may_use_gpu = device in ("cuda", "auto")
    if may_use_gpu and module.torch.cuda.is_available():
        module.torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    before = module.collect_gpu_evidence(gpu_required=may_use_gpu)
    before_mib = before.get("vram_allocated_bytes", 0) / (1024 * 1024)
    candidate_probs, pos_pred, resolved_device, fallback_reason = module.run_model_fold_internal(
        spec, train_df, params, seed, device, precision
    )
    duration = time.perf_counter() - started
    gpu = module.collect_gpu_evidence(gpu_required=may_use_gpu)
    after_mib = gpu.get("vram_allocated_bytes", 0) / (1024 * 1024)
    peak_mib = gpu.get("vram_peak_bytes", 0) / (1024 * 1024)
    peak_vram = max(0.0, after_mib - before_mib, peak_mib - before_mib)
    device_evidence = {
        "requested_device": device,
        "resolved_device": resolved_device,
        "cuda_available": gpu.get("cuda_available") if may_use_gpu else None,
        "gpu_used": resolved_device == "cuda" and peak_vram > 0,
        "vram_before_mib": before_mib if may_use_gpu else None,
        "vram_after_mib": after_mib if may_use_gpu else None,
        "fallback_reason": fallback_reason,
    }
    if candidate_probs.shape != (37,):
        raise ValueError(f"Normalized probabilities shape mismatch: {candidate_probs.shape}")
    if not module.np.isfinite(candidate_probs).all():
        raise ValueError("Normalized probabilities contain NaN or Inf")
    if (candidate_probs < 0.0).any():
        raise ValueError("Normalized probabilities contain negative values")

    recorder.record_prediction_ready(
        model_id=model_id,
        fold_id=fold_id,
        test_index=test_idx,
    )
    recorder.record_actual_read(
        model_id=model_id,
        fold_id=fold_id,
        test_index=test_idx,
    )
    leakage = module.execute_leakage_checks(
        spec,
        params,
        train_df,
        test_row,
        full_df,
        test_idx,
        candidate_probs,
        pos_pred,
        seed,
        device,
        precision,
    )
    return (
        candidate_probs,
        pos_pred,
        params,
        duration,
        peak_vram,
        leakage,
        device_evidence,
    )


__all__ = ["run_instrumented_fold"]

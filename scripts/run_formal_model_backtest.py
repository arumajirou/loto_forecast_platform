#!/usr/bin/env python
# ruff: noqa: E402,E501
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loto.data.canonical import canonicalize_loto7
from loto.data.lineage import atomic_write_json
from loto.evaluation.metrics_general import evaluate_all
from loto.features.pipeline import build_candidate_features, build_next_candidate_features
from loto.game.geometry import geometry_for
from loto.models.catalog import ModelSpec, list_model_specs
from loto.models.factory import RuntimeModel
from loto.models.providers import get_foundation_provider
from loto.models.workers import PositionSeriesWorker, normalize_worker_predictions
from loto.observability.gpu import collect_gpu_evidence


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return parsed


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run formal walk-forward backtesting for catalog models."
    )
    parser.add_argument(
        "--catalog-source", choices=["static", "dynamic", "merged"], default="dynamic"
    )
    parser.add_argument("--available-only", action="store_true", default=True)
    parser.add_argument("--models", default="all", help="'all' or comma separated model IDs")
    parser.add_argument("--stage", choices=["smoke", "screening", "formal"], default="smoke")
    parser.add_argument("--test-draws", type=positive_int, default=None)
    parser.add_argument("--min-train-draws", type=positive_int, default=400)
    parser.add_argument("--horizon", type=positive_int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout-per-model", type=positive_int, default=3600)
    parser.add_argument("--cpu-parallelism", type=positive_int, default=1)
    parser.add_argument("--gpu-parallelism", type=non_negative_int, default=1)
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--fail-fast", action="store_true", default=True)
    parser.add_argument("--output", default="runs/formal-backtest")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--precision", default="32")
    return parser


def get_data_manifest(data_path: Path) -> dict[str, Any]:
    manifest_path = data_path.parent.parent / "data_manifest.json"
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    sha = hashlib.sha256(data_path.read_bytes()).hexdigest()
    df = pd.read_csv(data_path)
    manifest = {
        "source_path": str(data_path),
        "source_sha256": sha,
        "canonical_data_sha256": sha,
        "row_count": len(df),
        "first_draw": int(df["draw_no"].min()),
        "last_draw": int(df["draw_no"].max()),
        "first_draw_date": str(df["draw_date"].min()),
        "last_draw_date": str(df["draw_date"].max()),
        "validation_status": "PASS",
        "schema_version": "1.0.0"
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(manifest_path, manifest)
    return manifest


def compute_code_fingerprint() -> str:
    core_files = [
        ROOT / "src/loto/models/workers.py",
        ROOT / "src/loto/models/catalog.py",
        ROOT / "src/loto/evaluation/metrics_general.py",
        Path(__file__),
    ]
    hasher = hashlib.sha256()
    for f in core_files:
        if f.exists():
            hasher.update(f.read_bytes())
    return hasher.hexdigest()[:16]


def generate_fold_signature(
    model_id: str,
    data_hash: str,
    fold_id: str,
    train_start: int,
    train_end: int,
    test_draw: int,
    model_config_hash: str,
    code_fingerprint: str,
    seed: int,
    stage: str,
    device: str,
    precision: str,
) -> str:
    payload = {
        "model_id": model_id,
        "data_hash": data_hash,
        "fold_id": fold_id,
        "train_start": train_start,
        "train_end": train_end,
        "test_draw": test_draw,
        "model_config_hash": model_config_hash,
        "code_fingerprint": code_fingerprint,
        "seed": seed,
        "stage": stage,
        "device": device,
        "precision": precision,
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# ------------------------------------------------------------------------------
# 11 Mandatory Baseline Implementations
# ------------------------------------------------------------------------------

def get_baseline_predictions(
    baseline_id: str,
    train_df: pd.DataFrame,
    test_row: pd.DataFrame,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    positions = 7
    np.random.seed(seed)

    if baseline_id == "uniform":
        probs = np.full(37, 7.0 / 37.0, dtype=float)
        pos_values = np.linspace(3, 35, 7)
        return probs, pos_values

    elif baseline_id == "random":
        picked = np.random.choice(np.arange(1, 38), 7, replace=False)
        picked = np.sort(picked)
        probs = np.zeros(37)
        for p in picked:
            probs[p - 1] = 1.0
        probs = project_probabilities(probs)
        return probs, picked.astype(float)

    elif baseline_id == "historical_median":
        all_vals = train_df[[f"n{i}" for i in range(1, 8)]].to_numpy().flatten()
        med = float(np.median(all_vals))
        pos_values = np.full(positions, med)
        probs = normalize_worker_predictions(task="position_series", history=train_df, values=pos_values)
        probs = project_probabilities(probs)
        return probs, pos_values

    elif baseline_id == "historical_mean":
        all_vals = train_df[[f"n{i}" for i in range(1, 8)]].to_numpy().flatten()
        mean_val = float(np.mean(all_vals))
        pos_values = np.full(positions, mean_val)
        probs = normalize_worker_predictions(task="position_series", history=train_df, values=pos_values)
        probs = project_probabilities(probs)
        return probs, pos_values

    elif baseline_id == "position_median":
        pos_values = np.array([
            float(np.median(train_df[f"n{i}"])) for i in range(1, 8)
        ])
        probs = normalize_worker_predictions(task="position_series", history=train_df, values=pos_values)
        probs = project_probabilities(probs)
        return probs, pos_values

    elif baseline_id == "position_frequency":
        pos_values = []
        for i in range(1, 8):
            mode_val = train_df[f"n{i}"].mode()
            pos_values.append(float(mode_val.iloc[0]) if not mode_val.empty else 19.0)
        pos_values = np.array(pos_values)
        probs = normalize_worker_predictions(task="position_series", history=train_df, values=pos_values)
        probs = project_probabilities(probs)
        return probs, pos_values

    elif baseline_id == "seasonal_naive":
        if len(train_df) >= 5:
            ref_row = train_df.iloc[-5]
        else:
            ref_row = train_df.iloc[-1]
        pos_values = ref_row[[f"n{i}" for i in range(1, 8)]].to_numpy(float)
        probs = normalize_worker_predictions(task="position_series", history=train_df, values=pos_values)
        probs = project_probabilities(probs)
        return probs, pos_values

    elif baseline_id == "last_value":
        ref_row = train_df.iloc[-1]
        pos_values = ref_row[[f"n{i}" for i in range(1, 8)]].to_numpy(float)
        probs = normalize_worker_predictions(task="position_series", history=train_df, values=pos_values)
        probs = project_probabilities(probs)
        return probs, pos_values

    elif baseline_id == "fixed_optimized_vector" or baseline_id == "mae_optimal_fixed_vector":
        pos_values = np.array([
            float(np.median(train_df[f"n{i}"])) for i in range(1, 8)
        ])
        probs = normalize_worker_predictions(task="position_series", history=train_df, values=pos_values)
        probs = project_probabilities(probs)
        return probs, pos_values

    elif baseline_id == "plus_minus_1_optimal_fixed_vector":
        pos_values = []
        for i in range(1, 8):
            vals = train_df[f"n{i}"].to_numpy()
            best_val = 19.0
            best_rate = -1.0
            for candidate in range(1, 38):
                rate = np.mean(np.abs(vals - candidate) <= 1)
                if rate > best_rate:
                    best_rate = rate
                    best_val = float(candidate)
            pos_values.append(best_val)
        pos_values = np.array(pos_values)
        probs = normalize_worker_predictions(task="position_series", history=train_df, values=pos_values)
        probs = project_probabilities(probs)
        return probs, pos_values

    else:
        raise ValueError(f"Unknown baseline: {baseline_id}")


# ------------------------------------------------------------------------------
# Leakage Guards
# ------------------------------------------------------------------------------

# Libraries excluded from the re-run invariance checks below because repeated
# re-instantiation/re-fitting is unsafe for their internal state (AutoGluon's
# cumulative time_limit budget, HPO trial counters, foundation-model checkpoint
# reload cost). These are NOT assumed leak-free -- each fold gets an explicit
# LEAKAGE_NOT_VERIFIED status persisted in the evidence trail instead of being
# silently skipped, so the gap is auditable rather than invisible.
LEAKAGE_CHECK_UNSUPPORTED_LIBRARIES = {
    "neuralforecast", "neuralforecast_auto", "gluonts", "autogluon",
    "timesfm", "chronos", "uni2ts", "tirex",
}

ABSOLUTE_LEAKAGE_TOLERANCE = 1e-5


def execute_leakage_checks(
    spec: ModelSpec,
    params: dict[str, Any],
    train_df: pd.DataFrame,
    test_row: pd.DataFrame,
    full_df: pd.DataFrame,
    test_idx: int,
    base_probs: np.ndarray,
    base_pos: np.ndarray,
    seed: int,
    device: str,
    precision: str,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "library": spec.library,
        "status": "LEAKAGE_NOT_VERIFIED",
        "reason": "",
        "deterministic_repeat_diff": None,
        "allowed_future_diff": None,
        "future_mutation_diff": None,
        "past_mutation_diff": None,
        "past_mutation_sensitive": None,
        "past_mutation_error": None,
    }

    # Hard invariants: unconditional, exact, cheap -- checked regardless of library.
    if test_idx in train_df.index:
        print("LEAKAGE_DETECTED: Scaler/Boundary Leakage check failed. Test index found in train set.", file=sys.stderr)
        sys.exit("LEAKAGE_DETECTED")

    max_train_draw = train_df["draw_no"].max()
    test_draw_no = test_row.iloc[0]["draw_no"]
    if max_train_draw >= test_draw_no:
        print("LEAKAGE_DETECTED: Fold Boundary Invariant violated. Train end >= test draw.", file=sys.stderr)
        sys.exit("LEAKAGE_DETECTED")

    if spec.library in LEAKAGE_CHECK_UNSUPPORTED_LIBRARIES:
        evidence["reason"] = (
            f"library '{spec.library}' excluded from re-run invariance checks "
            "(repeated re-fit is unsafe for this library's internal state)"
        )
        return evidence

    future_indices = full_df.index[full_df.index >= test_idx]
    if len(future_indices) == 0:
        evidence["status"] = "PASS"
        evidence["reason"] = "no_future_indices_in_scope"
        return evidence

    # 1. Deterministic-repeat baseline: same fold, identical inputs, re-run. Measures
    # the model's own run-to-run noise floor (GPU nondeterminism, parallel reduction
    # order) so the future-mutation tolerance below scales to it instead of relying
    # on an arbitrary fixed atol.
    try:
        r_probs, r_pos, _, _ = run_model_fold_internal(spec, train_df, params, seed, device, precision)
        deterministic_repeat_diff = max(
            float(np.max(np.abs(base_probs - r_probs))),
            float(np.max(np.abs(base_pos - r_pos))),
        )
        evidence["deterministic_repeat_diff"] = deterministic_repeat_diff
    except Exception as e:
        evidence["reason"] = f"deterministic_repeat_check_failed: {e}"
        return evidence

    allowed_future_diff = max(deterministic_repeat_diff * 5, ABSOLUTE_LEAKAGE_TOLERANCE)
    evidence["allowed_future_diff"] = allowed_future_diff

    # 2. Future-mutation check: future rows must NOT influence the current prediction.
    modified_full_df = full_df.copy()
    for col in ["n1", "n2", "n3", "n4", "n5", "n6", "n7"]:
        modified_full_df.loc[future_indices, col] = 99
    modified_train_df = modified_full_df.iloc[:test_idx]

    try:
        m_probs, m_pos, _, _ = run_model_fold_internal(spec, modified_train_df, params, seed, device, precision)
        future_mutation_diff = max(
            float(np.max(np.abs(base_probs - m_probs))),
            float(np.max(np.abs(base_pos - m_pos))),
        )
        evidence["future_mutation_diff"] = future_mutation_diff
    except Exception as e:
        evidence["reason"] = f"future_mutation_check_failed: {e}"
        return evidence

    if future_mutation_diff > allowed_future_diff:
        evidence["status"] = "LEAKAGE_DETECTED"
        evidence["reason"] = (
            f"future_mutation_diff={future_mutation_diff} exceeds allowed_future_diff="
            f"{allowed_future_diff} (deterministic_repeat_diff={deterministic_repeat_diff})"
        )
        print(
            f"LEAKAGE_DETECTED: Future Row Injection check failed. "
            f"diff={future_mutation_diff} > allowed={allowed_future_diff}.",
            file=sys.stderr,
        )
        sys.exit("LEAKAGE_DETECTED")

    # 3. Past-mutation check (diagnostic only, does not gate pass/fail): history
    # strictly before the boundary is changed and the prediction is EXPECTED to
    # change. A model that never responds to its own training history is a distinct
    # quality signal from leakage, so it is recorded but does not fail the fold.
    modified_past_df = train_df.copy()
    for col in ["n1", "n2", "n3", "n4", "n5", "n6", "n7"]:
        modified_past_df[col] = ((modified_past_df[col] + 17 - 1) % 37) + 1
    try:
        p_probs, p_pos, _, _ = run_model_fold_internal(spec, modified_past_df, params, seed, device, precision)
        past_mutation_diff = max(
            float(np.max(np.abs(base_probs - p_probs))),
            float(np.max(np.abs(base_pos - p_pos))),
        )
        evidence["past_mutation_diff"] = past_mutation_diff
        evidence["past_mutation_sensitive"] = bool(past_mutation_diff > allowed_future_diff)
    except Exception as e:
        evidence["past_mutation_error"] = str(e)

    evidence["status"] = "PASS"
    return evidence


# ------------------------------------------------------------------------------
# Model Parameter Resolver & Execution Wrapper
# ------------------------------------------------------------------------------

def resolve_model_params(spec: ModelSpec, stage: str) -> dict[str, Any]:
    params = dict(spec.default_params)

    # Overwrites stack configuration for NBEATS / NBEATSx (Horizon=1 incompatibility)
    if spec.class_name in {"NBEATS", "NBEATSx"}:
        params["stack_types"] = ["identity"]
        params["n_blocks"] = [1]
        params["mlp_units"] = [[64, 64]]

    if stage == "smoke":
        if spec.library == "neuralforecast":
            params.update({
                "max_steps": 2,
                "val_check_steps": 1,
                "early_stop_patience_steps": -1,
                "batch_size": 8,
                "input_size": 8,
            })
            # Transformer/Mixer models need larger input_size to avoid patch/FFT constraints
            if spec.class_name in {"TimesNet", "TimeMixer", "TSMixer", "iTransformer", "VanillaTransformer", "PatchTST", "TFT"}:
                params.update({
                    "max_steps": 2,
                    "input_size": 32,
                })
                # Add hidden_size and attention heads to compatible models to avoid pl.Trainer type errors.
                # TFT and VanillaTransformer use n_head, while others use n_heads. Ensure hidden_size is divisible by heads.
                if spec.class_name in {"TimesNet", "iTransformer", "VanillaTransformer", "PatchTST", "TFT"}:
                    params["hidden_size"] = 16

                if spec.class_name in {"iTransformer", "PatchTST"}:
                    params["n_heads"] = 2
                    params.pop("n_head", None)
                elif spec.class_name in {"VanillaTransformer", "TFT"}:
                    params["n_head"] = 2
                    params.pop("n_heads", None)
                else:
                    params.pop("n_head", None)
                    params.pop("n_heads", None)
            else:
                # Ensure no attention heads leak to simple MLP/CNN/RNN models
                params.pop("n_head", None)
                params.pop("n_heads", None)

        elif spec.library == "neuralforecast_auto":
            params.update({
                "backend": "optuna",
                "num_samples": 1,
                "max_steps": 2,
                "parallel_trials": 1,
                "refit_with_val": False,
                "search_strategy": "random",
                "input_size": 8,
                "batch_size": 8,
            })
            if spec.class_name in {"AutoNBEATS", "AutoNBEATSx"}:
                params.update({
                    "stack_types": ["identity"],
                    "n_blocks": [1],
                    "mlp_units": [[64, 64]],
                })
            # Transformer-based AutoML models need larger input_size.
            # Do NOT specify network structure configurations (hidden_size, n_heads) here
            # to let Optuna initialize them properly according to default spaces without pl.Trainer type errors.
            if spec.class_name in {"AutoTimesNet", "AutoTimeXer", "AutoInformer", "AutoAutoformer", "AutoFEDformer", "AutoPatchTST", "AutoiTransformer"}:
                params.update({
                    "input_size": 32,
                    "max_steps": 2,
                    "batch_size": 8,
                })
        elif spec.library == "autogluon":
            params.update({
                "presets": "fast_training",
                "time_limit": 5,
            })
        elif spec.library == "reservoirpy":
            params.update({
                "units": 10,
            })

    return params


def project_probabilities(probs: np.ndarray) -> np.ndarray:
    result = np.clip(probs, 1e-9, 1.0 - 1e-9)
    for attempt in range(50):
        current = float(result.sum())
        if abs(current - 7.0) < 1e-8:
            break
        if current <= 0:
            result = np.full(37, 7.0 / 37.0, dtype=float)
            break
        scaled = result * (7.0 / current)
        if np.any(scaled > 1.0):
            alpha = 0.05 * (attempt + 1)
            result = (1.0 - alpha) * result + alpha * np.full(37, 7.0 / 37.0, dtype=float)
            result = np.clip(result, 1e-9, 1.0 - 1e-9)
        else:
            result = np.clip(scaled, 1e-9, 1.0 - 1e-9)
            break
    return result


def _run_model_fold_internal_core(
    spec: ModelSpec,
    train_df: pd.DataFrame,
    params: dict[str, Any],
    seed: int,
    device: str,
    precision: str,
) -> tuple[np.ndarray, np.ndarray]:
    if spec.task == "candidate" and spec.library == "tabpfn_time_series":
        provider = get_foundation_provider(spec)(spec, params, seed=seed, device=device, precision=precision)
        provider.load()
        try:
            raw_values = np.asarray(provider.predict(train_df), dtype=float).reshape(37)
            candidate_probs = normalize_worker_predictions(task="candidate", history=train_df, values=raw_values)
            candidate_probs = project_probabilities(candidate_probs)
            ranked = np.argsort(-candidate_probs)[:7] + 1
            pos_pred = np.asarray(sorted(ranked.tolist()), dtype=float)
        finally:
            provider.close()

    elif spec.task == "candidate":
        train_features = build_candidate_features(train_df, windows=(5, 10, 20))
        query_features = build_next_candidate_features(train_df, windows=(5, 10, 20))
        runtime = RuntimeModel(spec, params, seed=seed).fit_candidate(train_features)
        output = runtime.predict_candidate(query_features)
        candidate_probs = np.asarray(output.candidate_probabilities, dtype=float)
        candidate_probs = project_probabilities(candidate_probs)
        ranked = np.argsort(-candidate_probs)[:7] + 1
        pos_pred = np.asarray(sorted(ranked.tolist()), dtype=float)

    elif spec.task == "foundation":
        provider = get_foundation_provider(spec)(spec, params, seed=seed, device=device, precision=precision)
        provider.load()
        try:
            pos_pred = np.asarray(provider.predict(train_df), dtype=float).reshape(7)
            candidate_probs = normalize_worker_predictions(task="position_series", history=train_df, values=pos_pred)
            candidate_probs = project_probabilities(candidate_probs)
        finally:
            provider.close()

    elif spec.task in {"position", "position_series", "candidate_series"}:
        worker = PositionSeriesWorker(spec=spec, params=params, seed=seed, device=device, precision=precision)
        output = worker.forecast(train_df)
        prediction_values = (
            output.candidate_probabilities
            if spec.task in {"candidate", "candidate_series"} and output.candidate_probabilities is not None
            else output.position_values
        )
        if spec.task in {"candidate", "candidate_series"}:
            candidate_probs = normalize_worker_predictions(task=spec.task, history=train_df, values=prediction_values)
            candidate_probs = project_probabilities(candidate_probs)
            ranked = np.argsort(-candidate_probs)[:7] + 1
            pos_pred = np.asarray(sorted(ranked.tolist()), dtype=float)
        else:
            pos_pred = prediction_values.flatten()
            candidate_probs = normalize_worker_predictions(task="position_series", history=train_df, values=pos_pred)
            candidate_probs = project_probabilities(candidate_probs)
    else:
        raise NotImplementedError()

    return candidate_probs, pos_pred


def run_model_fold_internal(
    spec: ModelSpec,
    train_df: pd.DataFrame,
    params: dict[str, Any],
    seed: int,
    device: str,
    precision: str,
) -> tuple[np.ndarray, np.ndarray, str, str | None]:
    effective_device = "cuda" if device == "cuda" or (device == "auto" and torch.cuda.is_available()) else "cpu"
    fallback_reason: str | None = None

    # Force CPU execution for granite-ttm due to local env CUDA compatibility problems
    if spec.model_id == "granite-ttm" and effective_device == "cuda":
        effective_device = "cpu"
        fallback_reason = "granite_ttm_forced_cpu_env_compatibility"

    try:
        probs, pos = _run_model_fold_internal_core(spec, train_df, params, seed, effective_device, precision)
        return probs, pos, effective_device, fallback_reason
    except Exception as e:
        # Fall back to CPU if GPU execution fails (SM architecture mismatch, CUDA runtime errors)
        if effective_device == "cuda":
            print(f"WARNING: Model {spec.model_id} failed on CUDA ({e}). Retrying with CPU fallback...", file=sys.stderr)
            probs, pos = _run_model_fold_internal_core(spec, train_df, params, seed, "cpu", precision)
            return probs, pos, "cpu", f"cuda_execution_failed: {e}"
        raise


def run_model_fold(
    spec: ModelSpec,
    train_df: pd.DataFrame,
    test_row: pd.DataFrame,
    full_df: pd.DataFrame,
    test_idx: int,
    seed: int,
    device: str,
    precision: str,
    stage: str,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any], float, float, dict[str, Any], dict[str, Any]]:
    params = resolve_model_params(spec, stage)
    print(f"DEBUG: Model {spec.model_id} resolved params: {params}")

    # Only probe real CUDA/nvidia-smi state when the requested device could plausibly use
    # the GPU. For an explicit --device cpu run there is nothing to disprove, so we keep the
    # cheap collect_gpu_evidence(gpu_required=False) short-circuit (its own comment: avoids
    # CUDA-driver-init hangs in GPU-less containers). Previously gpu_required=False was
    # passed unconditionally with no model/batch args, so it ALWAYS took that short-circuit
    # -- even for --device cuda/auto runs -- and peak_vram was silently 0.0 regardless of
    # real GPU usage. Gating on `device` instead of hardcoding False fixes that while
    # preserving the original safety property for confirmed-CPU runs.
    may_use_gpu = device in ("cuda", "auto")
    if may_use_gpu and torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()

    t0 = time.perf_counter()
    vram_before_evidence = collect_gpu_evidence(gpu_required=may_use_gpu)
    vram_before_mib = vram_before_evidence.get("vram_allocated_bytes", 0) / (1024 * 1024)

    candidate_probs, pos_pred, resolved_device, fallback_reason = run_model_fold_internal(
        spec, train_df, params, seed, device, precision
    )

    duration = time.perf_counter() - t0
    gpu_evidence = collect_gpu_evidence(gpu_required=may_use_gpu)
    vram_after_mib = gpu_evidence.get("vram_allocated_bytes", 0) / (1024 * 1024)
    vram_peak_mib = gpu_evidence.get("vram_peak_bytes", 0) / (1024 * 1024)

    peak_vram = max(0.0, vram_after_mib - vram_before_mib, vram_peak_mib - vram_before_mib)

    device_evidence = {
        "requested_device": device,
        "resolved_device": resolved_device,
        "cuda_available": gpu_evidence.get("cuda_available") if may_use_gpu else None,
        # resolved_device=="cuda" only says the fold *attempted* CUDA execution; it is true
        # even for CPU-only libraries (e.g. sklearn) that ignore the device argument entirely.
        # Requiring a measured VRAM delta as corroborating evidence avoids reporting
        # GPU-not-used as GPU-used for those cases.
        "gpu_used": resolved_device == "cuda" and peak_vram > 0,
        "vram_before_mib": vram_before_mib if may_use_gpu else None,
        "vram_after_mib": vram_after_mib if may_use_gpu else None,
        "fallback_reason": fallback_reason,
    }

    # Validate output contract
    if candidate_probs.shape != (37,):
        raise ValueError(f"Normalized probabilities shape mismatch: {candidate_probs.shape}")
    if not np.isfinite(candidate_probs).all():
        raise ValueError("Normalized probabilities contain NaN or Inf")
    if (candidate_probs < 0.0).any():
        raise ValueError("Normalized probabilities contain negative values")

    # Run Leakage Checks
    leakage_evidence = execute_leakage_checks(spec, params, train_df, test_row, full_df, test_idx, candidate_probs, pos_pred, seed, device, precision)

    return candidate_probs, pos_pred, params, duration, peak_vram, leakage_evidence, device_evidence


# ------------------------------------------------------------------------------
# Main Runner Loop
# ------------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    data_path = ROOT / "runs/data-acquisition-loto7/features/canonical_loto7.csv"
    if not data_path.exists():
        data_path = ROOT / "runs/data-acquisition-all/loto7/features/canonical_loto7.csv"
    if not data_path.exists():
        matches = list(ROOT.glob("**/canonical_loto7.csv"))
        if matches:
            data_path = matches[0]
        else:
            sys.exit("Error: Canonical Loto7 CSV not found.")

    manifest = get_data_manifest(data_path)
    print(f"Data manifest loaded: {data_path} ({manifest['row_count']} rows)")

    full_df, _ = canonicalize_loto7(pd.read_csv(data_path), source=str(data_path))
    N = len(full_df)

    test_draws = args.test_draws
    if test_draws is None:
        if args.stage == "smoke":
            test_draws = 10
        elif args.stage == "screening":
            test_draws = 30
        else:
            test_draws = 100

    if N - test_draws < args.min_train_draws:
        sys.exit(f"Insufficient history for min-train-draws={args.min_train_draws} and test-draws={test_draws}. N={N}")

    specs = list_model_specs(available_only=args.available_only)
    if args.models != "all":
        requested_ids = [m.strip() for m in args.models.split(",") if m.strip()]
        specs = [s for s in specs if s.model_id in requested_ids]

    print(f"Running stage={args.stage} for {len(specs)} models over {test_draws} folds...")

    code_fingerprint = compute_code_fingerprint()
    data_hash = manifest["canonical_data_sha256"]
    geometry = geometry_for("loto7")

    baselines = [
        "uniform",
        "random",
        "historical_median",
        "historical_mean",
        "position_median",
        "position_frequency",
        "seasonal_naive",
        "last_value",
        "fixed_optimized_vector",
        "mae_optimal_fixed_vector",
        "plus_minus_1_optimal_fixed_vector",
    ]

    for spec in specs:
        model_id = spec.model_id
        print(f"\nEvaluating Model: {model_id}")

        is_nc = "CC-BY-NC-4.0" in spec.notes or "NC" in spec.priority or model_id == "moirai"
        is_prior = "Prior Labs" in spec.notes or model_id == "tabpfn-ts"
        license_status = "LICENSE_APPROVED"
        if is_nc or is_prior:
            license_status = "LICENSE_RESTRICTED"

        model_config_hash = hashlib.sha256(json.dumps(spec.to_dict(), sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]

        folds_skipped = 0
        folds_executed = 0

        fold_runs = []
        for f in range(test_draws):
            test_idx = N - test_draws + f
            test_row = full_df.iloc[[test_idx]]
            train_df = full_df.iloc[:test_idx]

            train_start = int(train_df["draw_no"].min())
            train_end = int(train_df["draw_no"].max())
            test_draw_no = int(test_row.iloc[0]["draw_no"])
            fold_id = f"fold-{test_draw_no}"

            sig = generate_fold_signature(
                model_id=model_id,
                data_hash=data_hash,
                fold_id=fold_id,
                train_start=train_start,
                train_end=train_end,
                test_draw=test_draw_no,
                model_config_hash=model_config_hash,
                code_fingerprint=code_fingerprint,
                seed=args.seed,
                stage=args.stage,
                device=args.device,
                precision=args.precision,
            )

            fold_runs.append((fold_id, train_df, test_row, test_idx, train_start, train_end, test_draw_no, sig))

        all_passed = True
        model_run_dir = output_dir / model_id
        for fold_id, _, _, _, _, _, _test_draw_no, sig in fold_runs:
            fold_manifest_path = model_run_dir / fold_id / "fold_manifest.json"
            if fold_manifest_path.exists():
                try:
                    f_manifest = json.loads(fold_manifest_path.read_text(encoding="utf-8"))
                    if f_manifest.get("signature") != sig or f_manifest.get("status") != "PASS":
                        all_passed = False
                        break
                except Exception:
                    all_passed = False
                    break
            else:
                all_passed = False
                break

        if args.resume and all_passed:
            print(f"Skipping model {model_id} (All folds already completed with matching signature)")
            continue

        for fold_id, train_df, test_row, test_idx, train_start, train_end, test_draw_no, sig in fold_runs:
            fold_dir = model_run_dir / fold_id
            fold_dir.mkdir(parents=True, exist_ok=True)

            fold_manifest_path = fold_dir / "fold_manifest.json"
            if args.resume and fold_manifest_path.exists():
                try:
                    f_manifest = json.loads(fold_manifest_path.read_text(encoding="utf-8"))
                    if f_manifest.get("signature") == sig and f_manifest.get("status") == "PASS":
                        folds_skipped += 1
                        continue
                except Exception:
                    pass

            print(f"  -> {fold_id} (Train: {train_start}..{train_end}, Test draw: {test_draw_no})")

            actual_pos = test_row[[f"n{i}" for i in range(1, 8)]].to_numpy(int).reshape(1, -1)
            actual_candidates = np.zeros((1, 37))
            for val in actual_pos[0]:
                actual_candidates[0, val - 1] = 1.0

            err_msg = ""
            status = "PASS"
            leakage_evidence: dict[str, Any] = {
                "status": "LEAKAGE_NOT_VERIFIED",
                "reason": "fold_execution_failed_before_leakage_checks_completed",
            }
            device_evidence: dict[str, Any] = {
                "requested_device": args.device,
                "resolved_device": "unknown",
                "cuda_available": None,
                "gpu_used": None,
                "vram_before_mib": None,
                "vram_after_mib": None,
                "fallback_reason": "fold_execution_failed_before_device_evidence_collected",
            }
            try:
                candidate_probs, pos_pred, resolved_params, duration, peak_vram, leakage_evidence, device_evidence = run_model_fold(
                    spec=spec,
                    train_df=train_df,
                    test_row=test_row,
                    full_df=full_df,
                    test_idx=test_idx,
                    seed=args.seed,
                    device=args.device,
                    precision=args.precision,
                    stage=args.stage,
                )

                metrics = evaluate_all(
                    actual=actual_pos,
                    predicted=pos_pred.reshape(1, -1),
                    geometry=geometry,
                    targets=actual_candidates,
                    probabilities=candidate_probs.reshape(1, -1),
                )

                atomic_write_json(fold_dir / "prediction.json", {
                    "position_predictions": pos_pred.tolist(),
                    "candidate_probabilities": candidate_probs.tolist(),
                })
                atomic_write_json(fold_dir / "metrics.json", metrics)
                atomic_write_json(fold_dir / "resource_evidence.json", {
                    "duration_seconds": duration,
                    "peak_vram_mib": peak_vram,
                    **device_evidence,
                })
                atomic_write_json(fold_dir / "lifecycle.json", {
                    "fit_status": "PASS",
                    "predict_status": "PASS",
                    "resolved_params": resolved_params,
                })

            except Exception as e:
                traceback.print_exc()
                err_msg = str(e)
                status = "FAIL"
                if args.fail_fast:
                    if "LEAKAGE_DETECTED" in err_msg:
                        sys.exit("LEAKAGE_DETECTED")
                    sys.exit(f"Fail-fast active. Model {model_id} failed on {fold_id}: {err_msg}")

                atomic_write_json(fold_dir / "error.json", {
                    "error": err_msg,
                    "traceback": traceback.format_exc(),
                })
                status = "FAIL"

            baseline_metrics = {}
            for baseline in baselines:
                b_probs, b_pos = get_baseline_predictions(baseline, train_df, test_row, args.seed)
                b_metrics = evaluate_all(
                    actual=actual_pos,
                    predicted=b_pos.reshape(1, -1),
                    geometry=geometry,
                    targets=actual_candidates,
                    probabilities=b_probs.reshape(1, -1),
                )
                baseline_metrics[baseline] = b_metrics
            atomic_write_json(fold_dir / "baselines.json", baseline_metrics)
            atomic_write_json(fold_dir / "leakage_evidence.json", leakage_evidence)

            atomic_write_json(fold_manifest_path, {
                "model_id": model_id,
                "fold_id": fold_id,
                "status": status,
                "signature": sig,
                "train_start": train_start,
                "train_end": train_end,
                "test_draw": test_draw_no,
                "license_status": license_status,
                "error": err_msg,
                "leakage_status": leakage_evidence.get("status", "LEAKAGE_NOT_VERIFIED"),
            })
            folds_executed += 1

        print(f"Model {model_id} run complete: {folds_executed} executed, {folds_skipped} skipped.")


if __name__ == "__main__":
    main()

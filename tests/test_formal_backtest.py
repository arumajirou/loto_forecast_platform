from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import scripts.run_formal_model_backtest as rfmb
from loto.game.geometry import geometry_for
from loto.models.catalog import ModelSpec, list_model_specs
from scripts.aggregate_formal_backtest import bootstrap_ci, calculate_sign_test
from scripts.run_formal_model_backtest import (
    LEAKAGE_CHECK_UNSUPPORTED_LIBRARIES,
    compute_code_fingerprint,
    execute_leakage_checks,
    generate_fold_signature,
    get_baseline_predictions,
    resolve_model_params,
    run_model_fold,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def dummy_train_df():
    data = []
    # Create dummy sequential history of 20 draws for Loto7
    # n1..n7 must be sorted and distinct, n1 >= 1, n7 <= 37
    for idx in range(1, 21):
        data.append({
            "draw_id": f"loto7-{idx}",
            "draw_no": idx,
            "draw_date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=7 * idx),
            "n1": 2, "n2": 6, "n3": 11, "n4": 15, "n5": 20, "n6": 28, "n7": 34,
            "bonus1": 3, "bonus2": 15,
            "available_at": pd.Timestamp("2026-01-01") + pd.Timedelta(days=7 * idx),
        })
    return pd.DataFrame(data)


@pytest.fixture
def dummy_test_row():
    # draw 21
    return pd.DataFrame([{
        "draw_id": "loto7-21",
        "draw_no": 21,
        "draw_date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=7 * 21),
        "n1": 3, "n2": 7, "n3": 12, "n4": 16, "n5": 21, "n6": 29, "n7": 35,
        "bonus1": 4, "bonus2": 16,
        "available_at": pd.Timestamp("2026-01-01") + pd.Timedelta(days=7 * 21),
    }])


def test_walk_forward_signature():
    sig1 = generate_fold_signature(
        model_id="test-model",
        data_hash="data-hash-val",
        fold_id="fold-10",
        train_start=1,
        train_end=9,
        test_draw=10,
        model_config_hash="conf-hash",
        code_fingerprint="code-fp",
        seed=42,
        stage="smoke",
        device="cpu",
        precision="32",
    )
    sig2 = generate_fold_signature(
        model_id="test-model",
        data_hash="data-hash-val",
        fold_id="fold-10",
        train_start=1,
        train_end=9,
        test_draw=10,
        model_config_hash="conf-hash",
        code_fingerprint="code-fp",
        seed=42,
        stage="smoke",
        device="cpu",
        precision="32",
    )
    assert sig1 == sig2
    assert len(sig1) == 64  # SHA256 length hex


def test_code_fingerprint():
    fp = compute_code_fingerprint()
    assert len(fp) == 16
    assert isinstance(fp, str)


def test_baselines_generation(dummy_train_df, dummy_test_row):
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
    for b in baselines:
        probs, pos = get_baseline_predictions(
            baseline_id=b,
            train_df=dummy_train_df,
            test_row=dummy_test_row,
            seed=42,
        )
        # Check output shape contract
        assert probs.shape == (37,)
        assert pos.shape == (7,)
        # check probability constraints
        assert np.all(probs >= 0.0)
        assert abs(probs.sum() - 7.0) < 1e-4


def test_bootstrap_ci_stats():
    # Set up deterministic difference array
    diffs = np.array([0.5, 0.4, 0.6, 0.3, 0.5, 0.4, 0.7, 0.2, 0.5, 0.4])
    ci_low, ci_high = bootstrap_ci(diffs, num_resamples=200)
    assert ci_low < ci_high
    assert 0.2 <= ci_low <= 0.6
    assert 0.4 <= ci_high <= 0.8


def test_sign_test_stats():
    # 8 wins, 2 losses
    diffs = np.array([1, 1, 1, 1, 1, 1, 1, 1, -1, -1])
    pval = calculate_sign_test(diffs)
    assert 0.0 < pval < 0.2  # binomial test p-value


@pytest.fixture
def dummy_full_df_and_idx(dummy_train_df, dummy_test_row):
    full_df = pd.concat([dummy_train_df, dummy_test_row], ignore_index=True)
    test_idx = len(dummy_train_df)
    return full_df, test_idx


def _ridge_position_spec() -> ModelSpec:
    return next(s for s in list_model_specs(available_only=False) if s.model_id == "ridge-position")


def test_leakage_check_pass_for_simple_model(dummy_train_df, dummy_test_row, dummy_full_df_and_idx):
    full_df, test_idx = dummy_full_df_and_idx
    spec = _ridge_position_spec()
    params = resolve_model_params(spec, "smoke")
    base_probs, base_pos, *_ = run_model_fold(
        spec=spec,
        train_df=dummy_train_df,
        test_row=dummy_test_row,
        full_df=full_df,
        test_idx=test_idx,
        seed=42,
        device="cpu",
        precision="fp32",
        stage="smoke",
    )[:2]
    evidence = execute_leakage_checks(
        spec, params, dummy_train_df, dummy_test_row, full_df, test_idx,
        base_probs, base_pos, seed=42, device="cpu", precision="fp32",
    )
    assert evidence["status"] == "PASS"
    assert evidence["deterministic_repeat_diff"] is not None
    assert evidence["future_mutation_diff"] is not None


def test_leakage_check_not_verified_for_skip_listed_library(
    dummy_train_df, dummy_test_row, dummy_full_df_and_idx
):
    full_df, test_idx = dummy_full_df_and_idx
    skip_listed_library = next(iter(LEAKAGE_CHECK_UNSUPPORTED_LIBRARIES))
    fake_spec = ModelSpec(
        model_id="fake-skip-listed",
        family="fake",
        library=skip_listed_library,
        task="candidate",
        class_name="Fake",
    )
    evidence = execute_leakage_checks(
        fake_spec, {}, dummy_train_df, dummy_test_row, full_df, test_idx,
        np.zeros(37), np.zeros(7), seed=42, device="cpu", precision="fp32",
    )
    assert evidence["status"] == "LEAKAGE_NOT_VERIFIED"
    assert skip_listed_library in evidence["reason"]


def test_leakage_check_detects_future_injection(
    monkeypatch, dummy_train_df, dummy_test_row, dummy_full_df_and_idx
):
    full_df, test_idx = dummy_full_df_and_idx
    spec = _ridge_position_spec()
    base_probs = np.full(37, 1.0 / 37 * 7)
    base_pos = np.array([2.0, 6.0, 11.0, 15.0, 20.0, 28.0, 34.0])

    # execute_leakage_checks calls run_model_fold_internal with train_df bounded to
    # rows [:test_idx] every time (by construction, future rows are never in scope of
    # train_df, mutated or not) -- so a real leaky model can't be distinguished by
    # inspecting train_df's contents here. Instead simulate leakage by call order: the
    # 1st call is the deterministic-repeat baseline (must match base exactly), the 2nd
    # is the future-mutation probe. A model that diverges on the 2nd call despite
    # identical train_df is exactly what the check exists to catch.
    call_count = {"n": 0}

    def fake_run_model_fold_internal(spec, train_df, params, seed, device, precision):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return base_probs.copy(), base_pos.copy(), "cpu", None
        return base_pos.repeat(37 // 7 + 1)[:37], base_pos + 5.0, "cpu", None

    monkeypatch.setattr(rfmb, "run_model_fold_internal", fake_run_model_fold_internal)

    with pytest.raises(SystemExit, match="LEAKAGE_DETECTED"):
        rfmb.execute_leakage_checks(
            spec, {}, dummy_train_df, dummy_test_row, full_df, test_idx,
            base_probs, base_pos, seed=42, device="cpu", precision="fp32",
        )


def test_device_evidence_fields_cpu_device(dummy_train_df, dummy_test_row, dummy_full_df_and_idx):
    full_df, test_idx = dummy_full_df_and_idx
    spec = _ridge_position_spec()
    _, _, _, _, peak_vram, _, device_evidence = run_model_fold(
        spec=spec,
        train_df=dummy_train_df,
        test_row=dummy_test_row,
        full_df=full_df,
        test_idx=test_idx,
        seed=42,
        device="cpu",
        precision="fp32",
        stage="smoke",
    )
    assert device_evidence["requested_device"] == "cpu"
    assert device_evidence["resolved_device"] == "cpu"
    # A confirmed-CPU run must never probe CUDA -- these stay None (not measured),
    # not False/0.0, so "not measured" is distinguishable from "measured as absent."
    assert device_evidence["cuda_available"] is None
    assert device_evidence["gpu_used"] is False
    assert device_evidence["vram_before_mib"] is None
    assert device_evidence["vram_after_mib"] is None
    assert device_evidence["fallback_reason"] is None
    assert peak_vram == 0.0


def test_device_evidence_gpu_used_requires_vram_evidence(
    dummy_train_df, dummy_test_row, dummy_full_df_and_idx
):
    # ridge-position is a plain sklearn model that never touches CUDA regardless of the
    # requested device. Requesting --device cuda must not report gpu_used=True on the
    # strength of resolved_device alone -- that would violate "do not report GPU-not-used
    # as GPU-used" for every CPU-only-library model run under cuda/auto.
    full_df, test_idx = dummy_full_df_and_idx
    spec = _ridge_position_spec()
    _, _, _, _, peak_vram, _, device_evidence = run_model_fold(
        spec=spec,
        train_df=dummy_train_df,
        test_row=dummy_test_row,
        full_df=full_df,
        test_idx=test_idx,
        seed=42,
        device="cuda",
        precision="fp32",
        stage="smoke",
    )
    assert device_evidence["gpu_used"] is False
    if peak_vram <= 0:
        assert device_evidence["gpu_used"] is False


def test_formal_backtest_smoke_catalog_no_drift():
    """Phase 12 drift check: the frozen smoke config (Phase 10) is a reproducibility
    contract, not just a snapshot. If this test fails, either an unintentional
    parameter drift occurred (investigate and fix), or the drift is intentional (a
    smoke-parameter change) and configs/formal_backtest_smoke_catalog.json must be
    regenerated via scripts/freeze_formal_backtest_smoke_catalog.py -- never blindly.
    """
    catalog_path = ROOT / "configs" / "formal_backtest_smoke_catalog.json"
    frozen = json.loads(catalog_path.read_text())

    specs = {s.model_id: s for s in list_model_specs(available_only=False)}
    assert set(frozen["models"].keys()) == set(specs.keys())

    mismatches = []
    for model_id, frozen_entry in frozen["models"].items():
        spec = specs[model_id]
        current_hash = hashlib.sha256(
            json.dumps(spec.to_dict(), sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        if current_hash != frozen_entry["model_config_hash"]:
            mismatches.append(
                f"{model_id}: model_config_hash "
                f"{frozen_entry['model_config_hash']} -> {current_hash}"
            )
            continue
        try:
            current_params = resolve_model_params(spec, "smoke")
        except Exception as e:
            current_params = None
            if frozen_entry["resolve_error"] is None:
                mismatches.append(
                    f"{model_id}: now fails to resolve ({e}), frozen catalog had no error"
                )
            continue
        if frozen_entry["resolved_smoke_params"] != current_params:
            mismatches.append(
                f"{model_id}: resolved_smoke_params "
                f"{frozen_entry['resolved_smoke_params']} -> {current_params}"
            )

    assert not mismatches, "Smoke config drift detected:\n" + "\n".join(mismatches)


def test_geometry_mass_checks():
    geom = geometry_for("loto7")
    assert geom.positions == 7
    assert geom.universe_size == 37
    assert geom.expected_inclusion_mass == 7.0
    assert geom.is_legal([1, 2, 3, 4, 5, 6, 7]) is True
    assert geom.is_legal([1, 2, 3, 4, 5, 6, 38]) is False
    assert geom.is_legal([1, 2, 3, 4, 5, 6, 6]) is False  # duplicates

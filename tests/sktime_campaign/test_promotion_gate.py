from __future__ import annotations

from pathlib import Path

import pytest

from loto.sktime_campaign.promotion_gate import (
    CandidateMetrics,
    MetricSummary,
    PromotionGateRequest,
    PromotionPolicy,
    ProspectiveWindowEvidence,
    aggregate_all_evidence,
    run_promotion_gate,
)


def metrics(
    *,
    hit: float = 0.95,
    all_hit: float = 0.80,
    mae: float = 0.40,
    mse: float = 0.30,
    rmse: float = 0.55,
) -> CandidateMetrics:
    return CandidateMetrics(
        hit_at_1=MetricSummary(mean=hit, variance=0.0, worst=hit),
        all_position_hit_at_1=MetricSummary(
            mean=all_hit,
            variance=0.0,
            worst=all_hit,
        ),
        mae=MetricSummary(mean=mae, variance=0.0, worst=mae),
        mse=MetricSummary(mean=mse, variance=0.0, worst=mse),
        rmse=MetricSummary(mean=rmse, variance=0.0, worst=rmse),
    )


def window(
    index: int,
    *,
    drift: str = "STABLE",
    hit: float = 0.95,
    mae: float = 0.40,
    draw_count: int = 1,
) -> ProspectiveWindowEvidence:
    recommendation = {
        "STABLE": "CONTINUE_SHADOW",
        "WARNING": "CONTINUE_SHADOW_REVIEW_REQUIRED",
        "CRITICAL": "BLOCK_PROMOTION_RETRAIN_REVIEW_REQUIRED",
    }[drift]
    start = 2000 + (index * 10)
    return ProspectiveWindowEvidence(
        window_id=f"window-{index}",
        monitor_bundle_sha256=f"{index + 1:064x}",
        prediction_lock_seal_sha256=f"{index + 101:064x}",
        actuals_source_sha256=f"{index + 201:064x}",
        sealed_at_utc=f"2026-08-{index + 1:02d}T00:00:00Z",
        revealed_at_utc=f"2026-08-{index + 1:02d}T01:00:00Z",
        draw_no=list(range(start, start + draw_count)),
        shadow_candidate_id="mean",
        integrity_status="PASS",
        drift_status=drift,
        recommendation=recommendation,
        automatic_retraining=False,
        automatic_promotion=False,
        promotion_status="NOT_PROMOTED",
        shadow_metrics=metrics(hit=hit, mae=mae),
        baseline_metrics={
            "random_uniform": metrics(hit=0.50, mae=1.50),
            "last": metrics(hit=0.60, mae=1.20),
        },
    )


def request(
    tmp_path: Path,
    *,
    windows: list[ProspectiveWindowEvidence] | None = None,
    policy: PromotionPolicy | None = None,
) -> PromotionGateRequest:
    return PromotionGateRequest(
        output_dir=str(tmp_path / "p6"),
        run_id="p6-test",
        git_commit="abcdef1",
        code_sha256="1" * 64,
        config_sha256="2" * 64,
        shadow_candidate_id="mean",
        upstream_artifact_sha256={
            "p0": "3" * 64,
            "p1": "4" * 64,
            "p2": "5" * 64,
            "p3": "6" * 64,
            "p4": "7" * 64,
        },
        runtime_certification_status="PASS",
        leakage_audit_status="PASS",
        data_quality_status="PASS",
        seed_policy_status="PASS",
        preactual_lock_status="PASS",
        holdout_reference_metrics=metrics(hit=0.96, mae=0.35),
        windows=windows or [window(0), window(1), window(2)],
        policy=policy or PromotionPolicy(),
        human_approval_granted=False,
    )


def test_eligible_result_never_promotes_automatically(tmp_path: Path) -> None:
    result = run_promotion_gate(request(tmp_path))
    assert result["decision"] == "ELIGIBLE_FOR_HUMAN_APPROVAL"
    assert result["eligible_for_human_approval"] is True
    assert result["automatic_promotion"] is False
    assert result["registry_write_allowed"] is False
    assert result["promotion_status"] == "NOT_PROMOTED"


def test_insufficient_windows_are_blocked(tmp_path: Path) -> None:
    result = run_promotion_gate(
        request(tmp_path, windows=[window(0), window(1)])
    )
    assert result["decision"] == "BLOCKED_INSUFFICIENT_WINDOWS"


def test_insufficient_draws_are_blocked(tmp_path: Path) -> None:
    policy = PromotionPolicy(
        minimum_prospective_windows=3,
        minimum_total_draws=10,
    )
    result = run_promotion_gate(request(tmp_path, policy=policy))
    assert result["decision"] == "BLOCKED_INSUFFICIENT_DRAWS"


def test_warning_drift_is_blocked(tmp_path: Path) -> None:
    windows = [window(0), window(1, drift="WARNING"), window(2)]
    result = run_promotion_gate(request(tmp_path, windows=windows))
    assert result["decision"] == "BLOCKED_WARNING_DRIFT"


def test_critical_drift_is_blocked(tmp_path: Path) -> None:
    windows = [window(0), window(1, drift="CRITICAL"), window(2)]
    policy = PromotionPolicy(maximum_warning_windows=1)
    result = run_promotion_gate(
        request(tmp_path, windows=windows, policy=policy)
    )
    assert result["decision"] == "BLOCKED_CRITICAL_DRIFT"


def test_hit_target_is_blocked(tmp_path: Path) -> None:
    windows = [window(0, hit=0.80), window(1, hit=0.80), window(2, hit=0.80)]
    result = run_promotion_gate(request(tmp_path, windows=windows))
    assert result["decision"] == "BLOCKED_HIT_TARGET"


def test_worst_case_is_blocked(tmp_path: Path) -> None:
    windows = [window(0, hit=0.89), window(1), window(2)]
    policy = PromotionPolicy(minimum_weighted_hit_at_1=0.80)
    result = run_promotion_gate(
        request(tmp_path, windows=windows, policy=policy)
    )
    assert result["decision"] == "BLOCKED_WORST_CASE"


def test_holdout_hit_regression_is_blocked(tmp_path: Path) -> None:
    windows = [window(0, hit=0.90), window(1, hit=0.90), window(2, hit=0.90)]
    policy = PromotionPolicy(
        minimum_weighted_hit_at_1=0.80,
        minimum_worst_window_hit_at_1=0.80,
        maximum_hit_drop_from_holdout=0.01,
    )
    result = run_promotion_gate(
        request(tmp_path, windows=windows, policy=policy)
    )
    assert result["decision"] == "BLOCKED_HOLDOUT_REGRESSION"


def test_holdout_mae_regression_is_blocked(tmp_path: Path) -> None:
    windows = [window(0, mae=1.0), window(1, mae=1.0), window(2, mae=1.0)]
    policy = PromotionPolicy(maximum_mae_increase_from_holdout=0.10)
    result = run_promotion_gate(
        request(tmp_path, windows=windows, policy=policy)
    )
    assert result["decision"] == "BLOCKED_HOLDOUT_REGRESSION"


def test_baseline_superiority_is_required(tmp_path: Path) -> None:
    windows = []
    for index in range(3):
        item = window(index)
        payload = item.model_dump()
        payload["baseline_metrics"]["last"] = metrics(
            hit=0.99,
            mae=0.10,
        ).model_dump()
        windows.append(ProspectiveWindowEvidence.model_validate(payload))
    result = run_promotion_gate(request(tmp_path, windows=windows))
    assert result["decision"] == "BLOCKED_BASELINE_SUPERIORITY"


def test_overlapping_draws_are_rejected(tmp_path: Path) -> None:
    first = window(0)
    second = window(1)
    payload = second.model_dump()
    payload["draw_no"] = first.draw_no
    with pytest.raises(ValueError, match="overlapping"):
        request(
            tmp_path,
            windows=[
                first,
                ProspectiveWindowEvidence.model_validate(payload),
                window(2),
            ],
        )


def test_duplicate_lock_seals_are_rejected(tmp_path: Path) -> None:
    first = window(0)
    second = window(1)
    payload = second.model_dump()
    payload["prediction_lock_seal_sha256"] = (
        first.prediction_lock_seal_sha256
    )
    with pytest.raises(ValueError, match="seals"):
        request(
            tmp_path,
            windows=[
                first,
                ProspectiveWindowEvidence.model_validate(payload),
                window(2),
            ],
        )


def test_shadow_candidate_change_is_rejected(tmp_path: Path) -> None:
    changed = window(1)
    payload = changed.model_dump()
    payload["shadow_candidate_id"] = "median"
    with pytest.raises(ValueError, match="shadow"):
        request(
            tmp_path,
            windows=[
                window(0),
                ProspectiveWindowEvidence.model_validate(payload),
                window(2),
            ],
        )


def test_upstream_inventory_is_exact(tmp_path: Path) -> None:
    payload = request(tmp_path).model_dump()
    payload["upstream_artifact_sha256"].pop("p4")
    with pytest.raises(ValueError, match="P0-P4"):
        PromotionGateRequest.model_validate(payload)


def test_aggregate_is_weighted_by_draw_count(tmp_path: Path) -> None:
    windows = [
        window(0, hit=1.0, draw_count=1),
        window(1, hit=0.5, draw_count=3),
        window(2, hit=1.0, draw_count=1),
    ]
    aggregate = aggregate_all_evidence(request(tmp_path, windows=windows))
    assert aggregate["shadow_metrics"]["hit_at_1"]["mean"] == pytest.approx(0.7)
    assert aggregate["shadow_metrics"]["hit_at_1"]["worst"] == 0.5


def test_human_approval_cannot_be_pregranted(tmp_path: Path) -> None:
    payload = request(tmp_path).model_dump()
    payload["human_approval_granted"] = True
    with pytest.raises(ValueError):
        PromotionGateRequest.model_validate(payload)

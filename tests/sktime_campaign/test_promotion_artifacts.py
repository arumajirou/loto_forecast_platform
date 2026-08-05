from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.sktime_campaign.promotion_artifacts import (
    P6VerificationError,
    persist_p6,
    verify_p6,
)
from loto.sktime_campaign.promotion_gate import (
    CandidateMetrics,
    MetricSummary,
    PromotionGateRequest,
    PromotionPolicy,
    ProspectiveWindowEvidence,
)


def metrics(hit: float = 0.95, mae: float = 0.40) -> CandidateMetrics:
    return CandidateMetrics(
        hit_at_1=MetricSummary(mean=hit, variance=0.0, worst=hit),
        all_position_hit_at_1=MetricSummary(
            mean=0.80,
            variance=0.0,
            worst=0.80,
        ),
        mae=MetricSummary(mean=mae, variance=0.0, worst=mae),
        mse=MetricSummary(mean=0.30, variance=0.0, worst=0.30),
        rmse=MetricSummary(mean=0.55, variance=0.0, worst=0.55),
    )


def window(index: int) -> ProspectiveWindowEvidence:
    return ProspectiveWindowEvidence(
        window_id=f"window-{index}",
        monitor_bundle_sha256=f"{index + 1:064x}",
        prediction_lock_seal_sha256=f"{index + 101:064x}",
        actuals_source_sha256=f"{index + 201:064x}",
        sealed_at_utc=f"2026-08-{index + 1:02d}T00:00:00Z",
        revealed_at_utc=f"2026-08-{index + 1:02d}T01:00:00Z",
        draw_no=[3000 + index],
        shadow_candidate_id="mean",
        integrity_status="PASS",
        drift_status="STABLE",
        recommendation="CONTINUE_SHADOW",
        automatic_retraining=False,
        automatic_promotion=False,
        promotion_status="NOT_PROMOTED",
        shadow_metrics=metrics(),
        baseline_metrics={
            "random_uniform": metrics(hit=0.50, mae=1.50),
            "last": metrics(hit=0.60, mae=1.20),
        },
    )


def request(tmp_path: Path) -> PromotionGateRequest:
    return PromotionGateRequest(
        output_dir=str(tmp_path / "p6"),
        run_id="p6-artifact-test",
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
        windows=[window(0), window(1), window(2)],
        policy=PromotionPolicy(),
        human_approval_granted=False,
    )


def test_persist_and_verify_p6(tmp_path: Path) -> None:
    active = request(tmp_path)
    response = persist_p6(active)
    assert response["decision"] == "ELIGIBLE_FOR_HUMAN_APPROVAL"
    report = verify_p6(Path(active.output_dir), active)
    assert report["status"] == "PASS"
    assert report["promotion_status"] == "NOT_PROMOTED"


@pytest.mark.parametrize(
    "name",
    [
        "WINDOW_EVIDENCE.json",
        "AGGREGATED_METRICS.json",
        "RULE_EVALUATION.json",
        "PROMOTION_DECISION.json",
        "response.json",
    ],
)
def test_p6_tampering_is_detected(tmp_path: Path, name: str) -> None:
    active = request(tmp_path)
    persist_p6(active)
    path = Path(active.output_dir) / name
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(P6VerificationError):
        verify_p6(Path(active.output_dir), active)


def test_registry_write_tamper_is_detected(tmp_path: Path) -> None:
    active = request(tmp_path)
    persist_p6(active)
    path = Path(active.output_dir) / "PROMOTION_DECISION.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["registry_write_allowed"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(P6VerificationError):
        verify_p6(Path(active.output_dir), active)


def test_extra_artifact_breaks_sha_coverage(tmp_path: Path) -> None:
    active = request(tmp_path)
    persist_p6(active)
    (Path(active.output_dir) / "EXTRA.txt").write_text(
        "unexpected",
        encoding="utf-8",
    )
    with pytest.raises(P6VerificationError):
        verify_p6(Path(active.output_dir), active)

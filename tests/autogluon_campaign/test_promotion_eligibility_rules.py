from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.autogluon_campaign.promotion_eligibility import (
    PromotionPolicyV2,
    verify_promotion_eligibility,
)
from tests.autogluon_campaign.p17_test_support import (
    run_gate,
    score_bundle,
    valid_sources,
)


def test_eligible_when_all_rules_pass(tmp_path: Path) -> None:
    result = run_gate(tmp_path)
    assert result.status == "PASS"
    assert result.decision == "ELIGIBLE_FOR_HUMAN_APPROVAL"
    verified = verify_promotion_eligibility(Path(result.output_dir))
    assert verified["reason_code"] == "ALL_RULES_PASS"


def test_decision_never_promotes_or_writes_registry(tmp_path: Path) -> None:
    result = run_gate(tmp_path)
    decision = json.loads(Path(result.decision_path).read_text())
    assert decision["human_approval_required"] is True
    assert decision["human_approval_granted"] is False
    assert decision["automatic_promotion"] is False
    assert decision["automatic_retraining"] is False
    assert decision["registry_write_allowed"] is False
    assert decision["promotion_status"] == "NOT_PROMOTED"


def test_v2_null_relative_target_is_evaluated_as_implied_absolute_target(tmp_path: Path) -> None:
    holdout = score_bundle(
        tmp_path / "v2-holdout",
        stage="holdout",
        run_id="v2-holdout",
        draw_ids=[60],
        selected_hit=0.25,
        baseline_hit=0.10,
        game_id="numbers3",
    )
    prospective = [
        score_bundle(
            tmp_path / f"v2-p-{index}",
            stage="prospective",
            run_id=f"v2-p-{index}",
            draw_ids=[60 + index],
            selected_hit=0.25,
            baseline_hit=0.10,
            game_id="numbers3",
        )
        for index in (1, 2, 3)
    ]
    result = run_gate(
        tmp_path,
        holdout=holdout,
        prospective=prospective,
        policy=PromotionPolicyV2(game="numbers3"),
    )
    assert result.reason_code == "AGGREGATE_HIT_AT_1_TARGET"
    rule_payload = json.loads((Path(result.output_dir) / "RULE_EVALUATION.json").read_text())
    target_rule = next(
        row for row in rule_payload["rules"] if row["rule_id"] == "AGGREGATE_HIT_AT_1_TARGET"
    )
    assert target_rule["observed"] == pytest.approx(0.25)
    assert target_rule["requirement"] == pytest.approx(0.30)


def test_minimum_windows_blocks(tmp_path: Path) -> None:
    holdout, prospective = valid_sources(tmp_path)
    result = run_gate(tmp_path, holdout=holdout, prospective=prospective[:2])
    assert result.decision == "NOT_ELIGIBLE"
    assert result.reason_code == "MINIMUM_PROSPECTIVE_WINDOWS"


def test_warning_window_blocks(tmp_path: Path) -> None:
    holdout, prospective = valid_sources(tmp_path)
    prospective[0].rename(tmp_path / "warning")
    prospective[0] = score_bundle(
        prospective[0],
        stage="prospective",
        run_id="prospective-1",
        draw_ids=[12],
        drift_state="WARNING",
    )
    result = run_gate(tmp_path, holdout=holdout, prospective=prospective)
    assert result.reason_code == "ALL_WINDOWS_STABLE"


def test_aggregate_hit_target_blocks(tmp_path: Path) -> None:
    holdout, _ = valid_sources(tmp_path)
    prospective = [
        score_bundle(
            tmp_path / f"low-{index}",
            stage="prospective",
            run_id=f"low-{index}",
            draw_ids=[20 + index],
            selected_hit=0.80,
        )
        for index in (1, 2, 3)
    ]
    result = run_gate(tmp_path, holdout=holdout, prospective=prospective)
    assert result.reason_code == "AGGREGATE_HIT_AT_1_TARGET"


def test_worst_window_target_blocks(tmp_path: Path) -> None:
    holdout, _ = valid_sources(tmp_path)
    prospective = [
        score_bundle(
            tmp_path / "good-1",
            stage="prospective",
            run_id="good-1",
            draw_ids=[21],
            selected_hit=1.0,
        ),
        score_bundle(
            tmp_path / "good-2",
            stage="prospective",
            run_id="good-2",
            draw_ids=[22],
            selected_hit=1.0,
        ),
        score_bundle(
            tmp_path / "weak",
            stage="prospective",
            run_id="weak",
            draw_ids=[23],
            selected_hit=0.80,
        ),
    ]
    result = run_gate(tmp_path, holdout=holdout, prospective=prospective)
    assert result.reason_code == "WORST_WINDOW_HIT_AT_1_TARGET"


def test_holdout_hit_drop_blocks(tmp_path: Path) -> None:
    holdout = score_bundle(
        tmp_path / "holdout",
        stage="holdout",
        run_id="holdout",
        draw_ids=[1],
        selected_hit=1.0,
    )
    prospective = [
        score_bundle(
            tmp_path / f"p-{index}",
            stage="prospective",
            run_id=f"p-{index}",
            draw_ids=[index + 1],
            selected_hit=0.94,
        )
        for index in (1, 2, 3)
    ]
    result = run_gate(tmp_path, holdout=holdout, prospective=prospective)
    assert result.reason_code == "HOLDOUT_TO_PROSPECTIVE_HIT_DROP"


def test_holdout_mae_increase_blocks(tmp_path: Path) -> None:
    holdout = score_bundle(
        tmp_path / "holdout",
        stage="holdout",
        run_id="holdout",
        draw_ids=[1],
        selected_mae=0.10,
    )
    prospective = [
        score_bundle(
            tmp_path / f"p-{index}",
            stage="prospective",
            run_id=f"p-{index}",
            draw_ids=[index + 1],
            selected_mae=0.70,
        )
        for index in (1, 2, 3)
    ]
    result = run_gate(tmp_path, holdout=holdout, prospective=prospective)
    assert result.reason_code == "HOLDOUT_TO_PROSPECTIVE_MAE_INCREASE"


def test_baseline_superiority_is_required(tmp_path: Path) -> None:
    holdout, _ = valid_sources(tmp_path)
    prospective = [
        score_bundle(
            tmp_path / f"p-{index}",
            stage="prospective",
            run_id=f"p-{index}",
            draw_ids=[30 + index],
            selected_hit=0.95,
            selected_mae=0.30,
            baseline_hit=0.96,
            baseline_mae=0.20,
        )
        for index in (1, 2, 3)
    ]
    result = run_gate(tmp_path, holdout=holdout, prospective=prospective)
    assert result.reason_code == "ALL_BASELINES_BEATEN"

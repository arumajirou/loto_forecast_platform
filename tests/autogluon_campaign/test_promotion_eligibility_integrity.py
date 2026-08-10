from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from loto.autogluon_campaign.holdout_prospective import _write, _write_evidence
from loto.autogluon_campaign.promotion_eligibility import (
    PromotionEligibilityError,
    PromotionPolicy,
    PromotionPolicyV2,
    create_promotion_eligibility,
    verify_promotion_eligibility,
)
from tests.autogluon_campaign.p17_test_support import (
    run_gate,
    score_bundle,
    valid_sources,
)


def test_candidate_change_is_rejected(tmp_path: Path) -> None:
    holdout, prospective = valid_sources(tmp_path)
    prospective[0] = score_bundle(
        tmp_path / "different",
        stage="prospective",
        run_id="different",
        draw_ids=[40],
        candidate_id="DeepAR-known-static",
    )
    with pytest.raises(PromotionEligibilityError) as exc_info:
        run_gate(tmp_path, holdout=holdout, prospective=prospective)
    assert exc_info.value.code == "SHADOW_CANDIDATE_CHANGED"


def test_draw_overlap_is_rejected(tmp_path: Path) -> None:
    holdout, prospective = valid_sources(tmp_path)
    prospective[0] = score_bundle(
        tmp_path / "overlap",
        stage="prospective",
        run_id="overlap",
        draw_ids=[10],
    )
    with pytest.raises(PromotionEligibilityError) as exc_info:
        run_gate(tmp_path, holdout=holdout, prospective=prospective)
    assert exc_info.value.code == "DRAW_WINDOW_OVERLAP"


def test_duplicate_source_run_id_is_rejected(tmp_path: Path) -> None:
    holdout, prospective = valid_sources(tmp_path)
    prospective[0] = score_bundle(
        tmp_path / "duplicate-run",
        stage="prospective",
        run_id="prospective-2",
        draw_ids=[50],
    )
    with pytest.raises(PromotionEligibilityError) as exc_info:
        run_gate(tmp_path, holdout=holdout, prospective=prospective)
    assert exc_info.value.code == "SOURCE_RUN_ID_INVALID"


def test_upstream_tamper_is_rejected(tmp_path: Path) -> None:
    holdout, prospective = valid_sources(tmp_path)
    path = prospective[0] / "PER_PREDICTION_METRICS.json"
    path.write_text(path.read_text().replace("0.95", "0.10"))
    with pytest.raises(PromotionEligibilityError) as exc_info:
        run_gate(tmp_path, holdout=holdout, prospective=prospective)
    assert exc_info.value.code == "SCORE_FILE_HASH_MISMATCH"


def test_promotion_output_tamper_is_rejected(tmp_path: Path) -> None:
    result = run_gate(tmp_path)
    path = Path(result.output_dir) / "PROMOTION_DECISION.json"
    payload = json.loads(path.read_text())
    payload["registry_write_allowed"] = True
    path.write_text(json.dumps(payload))
    with pytest.raises(PromotionEligibilityError) as exc_info:
        verify_promotion_eligibility(Path(result.output_dir))
    assert exc_info.value.code == "PROMOTION_FILE_HASH_MISMATCH"


def test_policy_rejects_automatic_actions() -> None:
    with pytest.raises(ValueError):
        PromotionPolicy(automatic_promotion=True)
    with pytest.raises(ValueError):
        PromotionPolicy(automatic_retraining=True)
    with pytest.raises(ValueError):
        PromotionPolicy(registry_write_allowed=True)


def test_v2_effective_null_target_is_used_by_actual_rule_evaluation(tmp_path: Path) -> None:
    holdout = score_bundle(
        tmp_path / "holdout-v2-low",
        stage="holdout",
        run_id="holdout-v2-low",
        draw_ids=[10, 11],
        selected_hit=0.25,
        selected_mae=0.2,
        baseline_hit=0.10,
        baseline_mae=1.5,
        game_id="numbers3",
    )
    prospective = [
        score_bundle(
            tmp_path / f"prospective-v2-low-{index}",
            stage="prospective",
            run_id=f"prospective-v2-low-{index}",
            draw_ids=[20 + index],
            selected_hit=0.25,
            selected_mae=0.2,
            baseline_hit=0.10,
            baseline_mae=1.5,
            game_id="numbers3",
        )
        for index in (1, 2, 3)
    ]

    result = create_promotion_eligibility(
        holdout_score_dir=holdout,
        prospective_score_dirs=prospective,
        output_dir=tmp_path / "promotion-v2-low",
        policy=PromotionPolicyV2(game="numbers3"),
        run_id="v2-low",
        now=datetime(2026, 8, 10, 10, 0, tzinfo=UTC),
    )

    assert result.decision == "NOT_ELIGIBLE"
    decision = json.loads(Path(result.decision_path).read_text(encoding="utf-8"))
    assert decision["reason_code"] == "AGGREGATE_HIT_AT_1_TARGET"
    hit_rule = next(
        rule for rule in decision["rules"] if rule["rule_id"] == "AGGREGATE_HIT_AT_1_TARGET"
    )
    assert hit_rule["detail"]["observed"] == pytest.approx(0.25)
    assert hit_rule["detail"]["required"] == pytest.approx(0.30)


def test_v2_artifact_roundtrip_preserves_schema_policy_and_game(tmp_path: Path) -> None:
    holdout, prospective = valid_sources(tmp_path, game_id="numbers3")
    result = create_promotion_eligibility(
        holdout_score_dir=holdout,
        prospective_score_dirs=prospective,
        output_dir=tmp_path / "promotion-v2-roundtrip",
        policy=PromotionPolicyV2(game="numbers3"),
        run_id="v2-roundtrip",
        now=datetime(2026, 8, 10, 10, 0, tzinfo=UTC),
    )

    request = json.loads((Path(result.output_dir) / "REQUEST_METADATA.json").read_text())
    assert request["schema_version"] == "autogluon-promotion-eligibility-v2"
    assert request["policy"]["game"] == "numbers3"
    assert request["policy"]["tau"] == 1
    assert request["policy"]["hit_at_1_target_semantics"] == "excess_vs_iid_null"

    verified = verify_promotion_eligibility(Path(result.output_dir))
    assert verified["schema_version"] == "autogluon-promotion-eligibility-v2"
    assert verified["decision"] == "ELIGIBLE_FOR_HUMAN_APPROVAL"


def test_v2_rejects_scoring_evidence_from_the_wrong_game(tmp_path: Path) -> None:
    holdout, prospective = valid_sources(tmp_path, game_id="loto6")
    with pytest.raises(PromotionEligibilityError) as exc_info:
        create_promotion_eligibility(
            holdout_score_dir=holdout,
            prospective_score_dirs=prospective,
            output_dir=tmp_path / "promotion-v2-wrong-game",
            policy=PromotionPolicyV2(game="numbers3"),
            run_id="v2-wrong-game",
        )
    assert exc_info.value.code == "SCORING_GAME_POLICY_MISMATCH"


def test_v2_rejects_legacy_score_without_game_identity(tmp_path: Path) -> None:
    holdout, prospective = valid_sources(tmp_path, game_id=None)
    with pytest.raises(PromotionEligibilityError) as exc_info:
        create_promotion_eligibility(
            holdout_score_dir=holdout,
            prospective_score_dirs=prospective,
            output_dir=tmp_path / "promotion-v2-missing-game",
            policy=PromotionPolicyV2(game="numbers3"),
            run_id="v2-missing-game",
        )
    assert exc_info.value.code == "SCORING_GAME_MISSING"


def test_rehashed_semantic_candidate_tamper_is_rejected(tmp_path: Path) -> None:
    result = run_gate(tmp_path)
    root = Path(result.output_dir)
    path = root / "WINDOW_EVIDENCE.json"
    payload = json.loads(path.read_text())
    payload["prospective"][0]["selected_candidate_id"] = "DeepAR-known-static"
    _write(path, payload)
    payload_names = [
        "REQUEST_METADATA.json",
        "UPSTREAM_LINEAGE.json",
        "WINDOW_EVIDENCE.json",
        "AGGREGATED_METRICS.json",
        "RULE_EVALUATION.json",
        "PROMOTION_DECISION.json",
        "response.json",
    ]
    _write_evidence(root, payload_names)
    with pytest.raises(PromotionEligibilityError) as exc_info:
        verify_promotion_eligibility(root)
    assert exc_info.value.code == "SHADOW_CANDIDATE_CHANGED"


def test_fixed_time_output_is_deterministic(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_holdout, first_prospective = valid_sources(first_root)
    second_holdout, second_prospective = valid_sources(second_root)
    fixed_time = datetime(2026, 8, 5, 10, 0, tzinfo=UTC)
    first = create_promotion_eligibility(
        holdout_score_dir=first_holdout,
        prospective_score_dirs=first_prospective,
        output_dir=first_root / "promotion",
        run_id="deterministic",
        now=fixed_time,
    )
    second = create_promotion_eligibility(
        holdout_score_dir=second_holdout,
        prospective_score_dirs=second_prospective,
        output_dir=second_root / "promotion",
        run_id="deterministic",
        now=fixed_time,
    )
    first_files = {
        path.name: path.read_bytes() for path in Path(first.output_dir).iterdir() if path.is_file()
    }
    second_files = {
        path.name: path.read_bytes() for path in Path(second.output_dir).iterdir() if path.is_file()
    }
    assert first_files == second_files


def test_cli_create_and_verify_eligible(tmp_path: Path, capsys) -> None:
    from loto.autogluon_campaign.promotion_eligibility_cli import main

    holdout, prospective = valid_sources(tmp_path)
    output = tmp_path / "cli-promotion"
    args = [
        "create",
        "--holdout-score",
        str(holdout),
        "--output",
        str(output),
        "--run-id",
        "cli-run",
    ]
    for path in prospective:
        args.extend(["--prospective-score", str(path)])
    assert main(args) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["decision"] == "ELIGIBLE_FOR_HUMAN_APPROVAL"
    assert main(["verify", "--run", str(output)]) == 0


def test_cli_v2_policy_create_and_verify(tmp_path: Path, capsys) -> None:
    from loto.autogluon_campaign.promotion_eligibility_cli import main

    holdout, prospective = valid_sources(tmp_path, game_id="numbers3")
    policy_path = tmp_path / "policy-v2.json"
    policy_path.write_text(PromotionPolicyV2(game="numbers3").model_dump_json(), encoding="utf-8")
    output = tmp_path / "cli-promotion-v2"
    args = [
        "create",
        "--holdout-score",
        str(holdout),
        "--output",
        str(output),
        "--run-id",
        "cli-v2",
        "--policy",
        str(policy_path),
    ]
    for path in prospective:
        args.extend(["--prospective-score", str(path)])
    assert main(args) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["decision"] == "ELIGIBLE_FOR_HUMAN_APPROVAL"
    request = json.loads((output / "REQUEST_METADATA.json").read_text())
    assert request["schema_version"] == "autogluon-promotion-eligibility-v2"
    assert main(["verify", "--run", str(output)]) == 0


def test_cli_returns_two_for_not_eligible(tmp_path: Path, capsys) -> None:
    from loto.autogluon_campaign.promotion_eligibility_cli import main

    holdout, prospective = valid_sources(tmp_path)
    output = tmp_path / "cli-blocked"
    args = [
        "create",
        "--holdout-score",
        str(holdout),
        "--prospective-score",
        str(prospective[0]),
        "--prospective-score",
        str(prospective[1]),
        "--output",
        str(output),
        "--run-id",
        "cli-blocked",
    ]
    assert main(args) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "NOT_ELIGIBLE"


def test_cli_returns_two_for_invalid_source(tmp_path: Path, capsys) -> None:
    from loto.autogluon_campaign.promotion_eligibility_cli import main

    assert (
        main(
            [
                "create",
                "--holdout-score",
                str(tmp_path / "missing"),
                "--prospective-score",
                str(tmp_path / "missing-p"),
                "--output",
                str(tmp_path / "output"),
                "--run-id",
                "invalid",
            ]
        )
        == 2
    )
    payload = json.loads(capsys.readouterr().err)
    assert payload["status"] == "FAILED"

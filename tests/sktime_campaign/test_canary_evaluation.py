from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from loto.sktime_campaign.canary_evaluation import (
    CanaryEvaluationRequest,
    evaluate_shadow_canary,
)
from tests.sktime_campaign.p10_helpers import (
    SHADOW_ID,
    make_request,
    make_window_payload,
    reseal_window_payload,
)


def test_eligible_canary_uses_primary_and_secondary_metrics(tmp_path) -> None:
    result = evaluate_shadow_canary(make_request(tmp_path / "out"))
    assert result["decision"] == "ELIGIBLE_FOR_PRIMARY_PROMOTION_REVIEW"
    shadow = result["candidate_metrics"][SHADOW_ID]
    assert shadow["mean"]["hit_at_1"] == 1.0
    assert shadow["mean"]["all_position_hit_at_1"] == 1.0
    assert shadow["mean"]["mae"] == 0.0
    assert shadow["mean"]["mse"] == 0.0
    assert shadow["mean"]["rmse"] == 0.0
    assert shadow["mean"]["position_hit_at_1"] == [1.0, 1.0]
    assert result["primary_promotion_executed"] is False


def test_insufficient_windows_is_ordered_first(tmp_path) -> None:
    request = make_request(tmp_path / "out", windows=2)
    result = evaluate_shadow_canary(request)
    assert result["decision"] == "BLOCKED_INSUFFICIENT_WINDOWS"


def test_weighted_hit_target_rejects(tmp_path) -> None:
    request = make_request(tmp_path / "out")
    payload = request.model_dump(mode="json")
    payload["windows"][0] = make_window_payload(1, shadow_values=[[9, 9]])
    result = evaluate_shadow_canary(CanaryEvaluationRequest.model_validate(payload))
    assert result["decision"] == "REJECTED_PRIMARY_HIT_TARGET"


def test_worst_window_rule_rejects_even_when_weighted_target_is_relaxed(tmp_path) -> None:
    request = make_request(tmp_path / "out")
    payload = request.model_dump(mode="json")
    payload["policy"]["minimum_weighted_hit_at_1"] = 0.0
    payload["windows"][0] = make_window_payload(1, shadow_values=[[9, 9]])
    result = evaluate_shadow_canary(CanaryEvaluationRequest.model_validate(payload))
    assert result["decision"] == "REJECTED_WORST_WINDOW"


def test_mae_limit_rejects(tmp_path) -> None:
    request = make_request(tmp_path / "out")
    payload = request.model_dump(mode="json")
    payload["policy"]["minimum_weighted_hit_at_1"] = 0.0
    payload["policy"]["minimum_worst_window_hit_at_1"] = 0.0
    payload["policy"]["maximum_weighted_mae"] = 0.1
    payload["windows"][0] = make_window_payload(1, shadow_values=[[4, 7]])
    result = evaluate_shadow_canary(CanaryEvaluationRequest.model_validate(payload))
    assert result["decision"] == "REJECTED_MAE_LIMIT"


def test_baseline_superiority_rejects(tmp_path) -> None:
    request = make_request(tmp_path / "out")
    payload = request.model_dump(mode="json")
    for index in range(3):
        actual = payload["windows"][index]["actuals"]
        payload["windows"][index] = make_window_payload(
            index + 1,
            shadow_values=[[9, 9]],
            baseline_values=actual,
        )
    payload["policy"]["minimum_weighted_hit_at_1"] = 0.0
    payload["policy"]["minimum_worst_window_hit_at_1"] = 0.0
    payload["policy"]["maximum_weighted_mae"] = 10.0
    result = evaluate_shadow_canary(CanaryEvaluationRequest.model_validate(payload))
    assert result["decision"] == "REJECTED_BASELINE_SUPERIORITY"


def test_no_strict_improvement_rejects_equal_candidates(tmp_path) -> None:
    request = make_request(tmp_path / "out")
    payload = request.model_dump(mode="json")
    for index in range(3):
        actual = payload["windows"][index]["actuals"]
        payload["windows"][index] = make_window_payload(
            index + 1,
            shadow_values=actual,
            baseline_values=actual,
        )
    result = evaluate_shadow_canary(CanaryEvaluationRequest.model_validate(payload))
    assert result["decision"] == "REJECTED_NO_STRICT_BASELINE_IMPROVEMENT"


def test_random_baseline_aggregates_all_three_seeds(tmp_path) -> None:
    result = evaluate_shadow_canary(make_request(tmp_path / "out"))
    random = result["candidate_metrics"]["random"]
    assert random["seed_count"] == 3
    assert len(random["seed_summaries"]) == 3
    assert "variance" in random
    assert "worst" in random


def test_prediction_lock_tamper_is_rejected(tmp_path) -> None:
    request = make_request(tmp_path / "out")
    payload = request.model_dump(mode="json")
    payload["windows"][0]["predictions"][0]["values"] = [[9, 9]]
    with pytest.raises(ValidationError, match="prediction lock SHA-256 mismatch"):
        CanaryEvaluationRequest.model_validate(payload)


def test_actual_reveal_before_lock_is_rejected(tmp_path) -> None:
    request = make_request(tmp_path / "out")
    payload = request.model_dump(mode="json")
    payload["windows"][0]["actuals_revealed_at_utc"] = "2026-08-01T00:00:00Z"
    with pytest.raises(ValidationError, match="actual reveal must follow"):
        CanaryEvaluationRequest.model_validate(payload)


def test_overlapping_draw_ids_are_rejected(tmp_path) -> None:
    request = make_request(tmp_path / "out")
    payload = request.model_dump(mode="json")
    changed = copy.deepcopy(payload["windows"][1])
    changed["draw_ids"] = payload["windows"][0]["draw_ids"]
    payload["windows"][1] = reseal_window_payload(changed)
    with pytest.raises(ValidationError, match="draw IDs may not overlap"):
        CanaryEvaluationRequest.model_validate(payload)


def test_changed_activation_is_rejected(tmp_path) -> None:
    request = make_request(tmp_path / "out")
    payload = request.model_dump(mode="json")
    changed = copy.deepcopy(payload["windows"][0])
    changed["activation_id"] = "2" * 64
    changed["prediction_lock_sha256"] = make_window_payload(1)["prediction_lock_sha256"]
    payload["windows"][0] = changed
    with pytest.raises(ValidationError):
        CanaryEvaluationRequest.model_validate(payload)


def test_required_baseline_inventory_is_enforced(tmp_path) -> None:
    request = make_request(tmp_path / "out")
    payload = request.model_dump(mode="json")
    changed = copy.deepcopy(payload["windows"][0])
    changed["predictions"] = [
        item for item in changed["predictions"] if item["candidate_id"] != "frequency"
    ]
    payload["windows"][0] = reseal_window_payload(changed)
    with pytest.raises(ValidationError, match="baseline inventory"):
        CanaryEvaluationRequest.model_validate(payload)


def test_random_seed_inventory_is_enforced(tmp_path) -> None:
    request = make_request(tmp_path / "out")
    payload = request.model_dump(mode="json")
    changed = copy.deepcopy(payload["windows"][0])
    random_rows = [item for item in changed["predictions"] if item["candidate_id"] == "random"]
    random_rows[2]["seed"] = 4
    payload["windows"][0] = reseal_window_payload(changed)
    with pytest.raises(ValidationError, match="random baseline"):
        CanaryEvaluationRequest.model_validate(payload)

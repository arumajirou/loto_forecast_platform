from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from loto.adapters.tabpfn_ts import (
    CandidateProbability,
    CandidateScore,
    ForecastValue,
    QuantileForecast,
    TabPFNTSResponseV2,
    TaskFormulation,
    rank_candidate_scores,
    validate_calibrated_probabilities,
)
from .conftest import (
    build_candidate_response,
    build_position_response,
)


def test_position_response_preserves_series_and_horizon_identity() -> None:
    response = build_position_response(prediction_length=5)
    assert len(response.point_forecast) == 15
    assert response.prediction_index == [1, 2, 3, 4, 5]


def test_non_finite_point_output_is_rejected() -> None:
    payload = build_position_response().model_dump(mode="json")
    payload["point_forecast"][0]["value"] = math.nan
    with pytest.raises(ValidationError):
        TabPFNTSResponseV2.model_validate(payload)


def test_quantile_crossing_is_rejected() -> None:
    payload = build_position_response().model_dump(mode="json")
    payload["quantiles"][0]["values"][0]["value"] = 1000.0
    with pytest.raises(ValidationError, match="quantile crossing"):
        TabPFNTSResponseV2.model_validate(payload)


def test_quantile_shape_mismatch_is_rejected() -> None:
    payload = build_position_response().model_dump(mode="json")
    payload["quantiles"][0]["values"].pop()
    with pytest.raises(ValidationError, match="shape does not match"):
        TabPFNTSResponseV2.model_validate(payload)


def test_negative_raw_candidate_scores_are_valid_and_not_probabilities() -> None:
    response = build_candidate_response()
    assert any(
        item.raw_candidate_regression_score < 0 for item in response.raw_candidate_scores or []
    )
    dumped = response.model_dump(mode="json")
    assert "raw_candidate_scores" in dumped
    assert "candidate_probabilities" not in dumped


def test_candidate_ranking_has_distinct_ranked_and_sorted_variants() -> None:
    response = build_candidate_response()
    ranked, sorted_positions = rank_candidate_scores(
        response.raw_candidate_scores or [], response.effective_arguments.game_geometry
    )
    assert ranked == [4, 2]
    assert sorted_positions == [2, 4]


def test_calibrated_probabilities_require_candidate_coverage_and_sum() -> None:
    geometry = build_candidate_response().effective_arguments.game_geometry
    probabilities = [
        CandidateProbability(candidate=1, calibrated_probability=0.1),
        CandidateProbability(candidate=2, calibrated_probability=0.6),
        CandidateProbability(candidate=3, calibrated_probability=0.2),
        CandidateProbability(candidate=4, calibrated_probability=0.9),
        CandidateProbability(candidate=5, calibrated_probability=0.2),
    ]
    validate_calibrated_probabilities(probabilities, geometry)

    bad = probabilities[:-1]
    with pytest.raises(ValueError, match="each candidate exactly once"):
        validate_calibrated_probabilities(bad, geometry)


def test_uncalibrated_values_cannot_enter_probability_field() -> None:
    with pytest.raises(ValidationError):
        CandidateProbability(candidate=1, calibrated_probability=-0.01)
    CandidateScore(candidate=1, raw_candidate_regression_score=-0.01)


def test_position_response_rejects_candidate_score_payload() -> None:
    payload = build_position_response().model_dump(mode="json")
    payload["raw_candidate_scores"] = [
        {"candidate": index, "raw_candidate_regression_score": 0.0}
        for index in range(10)
    ]
    with pytest.raises(ValidationError, match="must not contain candidate scores"):
        TabPFNTSResponseV2.model_validate(payload)


def test_quantile_level_must_match_effective_arguments() -> None:
    response = build_position_response()
    payload = response.model_dump(mode="json")
    payload["quantiles"] = [
        QuantileForecast(
            level=0.2,
            values=[
                ForecastValue(
                    series_id=item.series_id,
                    horizon_step=item.horizon_step,
                    value=item.value,
                )
                for item in response.point_forecast
            ],
        ).model_dump(mode="json")
    ]
    with pytest.raises(ValidationError, match="do not match effective arguments"):
        TabPFNTSResponseV2.model_validate(payload)


def test_task_formulation_is_not_silently_reinterpreted() -> None:
    payload = build_candidate_response().model_dump(mode="json")
    payload["task_formulation"] = TaskFormulation.POSITION_BATCH.value
    with pytest.raises(ValidationError):
        TabPFNTSResponseV2.model_validate(payload)


def test_status_ok_rejects_blocked_ts3_lane() -> None:
    payload = build_position_response().model_dump(mode="json")
    payload["model_identity"].update(
        {
            "checkpoint_lane": "ts3_current",
            "repo_id": None,
            "revision": None,
            "checkpoint_filename": "tabpfn-v3-regressor-v3_20260506_timeseries.ckpt",
            "checkpoint_sha256": None,
        }
    )
    payload["artifact_reference"]["weight_sha256"] = None
    payload["license_evidence"].update(
        {
            "weight_license": None,
            "attribution_required": None,
            "license_accepted": False,
        }
    )
    with pytest.raises(ValidationError, match="checkpoint lane is not executable"):
        TabPFNTSResponseV2.model_validate(payload)


def test_status_ok_requires_exact_v2_checkpoint_identity() -> None:
    payload = build_position_response().model_dump(mode="json")
    payload["model_identity"]["checkpoint_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="executable lane manifest"):
        TabPFNTSResponseV2.model_validate(payload)


def test_status_ok_requires_checkpoint_license_acceptance() -> None:
    payload = build_position_response().model_dump(mode="json")
    payload["license_evidence"]["license_accepted"] = False
    with pytest.raises(ValidationError, match="license acceptance is required"):
        TabPFNTSResponseV2.model_validate(payload)


def test_runtime_and_gpu_provider_pid_must_match() -> None:
    payload = build_position_response().model_dump(mode="json")
    payload["runtime_evidence"]["provider_pid"] = 456
    with pytest.raises(ValidationError, match="provider PID differs"):
        TabPFNTSResponseV2.model_validate(payload)


def test_feature_manifest_identity_must_match_effective_arguments() -> None:
    payload = build_position_response().model_dump(mode="json")
    payload["feature_manifest"]["feature_set_id"] = "different-feature-set"
    with pytest.raises(ValidationError, match="feature_set_id differs"):
        TabPFNTSResponseV2.model_validate(payload)


def test_point_forecast_rejects_duplicate_series_horizon_pair() -> None:
    payload = build_position_response().model_dump(mode="json")
    payload["point_forecast"].append(dict(payload["point_forecast"][0]))
    with pytest.raises(ValidationError, match="exactly once"):
        TabPFNTSResponseV2.model_validate(payload)


def test_quantile_forecast_rejects_duplicate_series_horizon_pair() -> None:
    payload = build_position_response().model_dump(mode="json")
    payload["quantiles"][0]["values"].append(dict(payload["quantiles"][0]["values"][0]))
    with pytest.raises(ValidationError, match="exactly once"):
        TabPFNTSResponseV2.model_validate(payload)


def test_candidate_response_is_explicitly_one_step() -> None:
    payload = build_candidate_response().model_dump(mode="json")
    payload["effective_arguments"]["prediction_length"] = 2
    payload["prediction_index"] = [1, 2]
    with pytest.raises(ValidationError, match="prediction_length=1 only"):
        TabPFNTSResponseV2.model_validate(payload)

from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.adapters.tabpfn_ts import (
    CheckpointLane,
    ExecutionStatus,
    KnownFutureCovariateRow,
    TaskFormulation,
    lane_manifest,
)

from .conftest import build_position_request


def test_request_rejects_unknown_top_level_key() -> None:
    payload = build_position_request().model_dump(mode="json")
    payload["surprise"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        build_position_request().__class__.model_validate(payload)


@pytest.mark.parametrize("horizon", [1, 2, 5])
def test_supported_horizons(horizon: int) -> None:
    request = build_position_request(prediction_length=horizon)
    assert request.prediction_length == horizon


def test_unsupported_horizon_rejected() -> None:
    payload = build_position_request().model_dump(mode="json")
    payload["prediction_length"] = 3
    with pytest.raises(ValidationError):
        build_position_request().__class__.model_validate(payload)


def test_past_only_covariates_are_fail_closed() -> None:
    payload = build_position_request().model_dump(mode="json")
    payload["past_only_covariates"] = [{"lagged_weather": 1.0}]
    with pytest.raises(ValidationError, match="UNSUPPORTED_BY_UPSTREAM: past-only"):
        build_position_request().__class__.model_validate(payload)


def test_static_covariates_are_fail_closed() -> None:
    payload = build_position_request().model_dump(mode="json")
    payload["static_covariates"] = {"game": "toy3"}
    with pytest.raises(ValidationError, match="UNSUPPORTED_BY_UPSTREAM: static"):
        build_position_request().__class__.model_validate(payload)


def test_known_future_covariates_are_explicitly_supported() -> None:
    request = build_position_request(prediction_length=2).model_copy(
        update={
            "known_future_covariates": [
                KnownFutureCovariateRow(
                    horizon_step=1,
                    timestamp="4",
                    values={"draw_no": 4, "weekday": 2},
                ),
                KnownFutureCovariateRow(
                    horizon_step=2,
                    timestamp="5",
                    values={"draw_no": 5, "weekday": 4},
                ),
            ]
        }
    )
    validated = request.__class__.model_validate(request.model_dump(mode="json"))
    assert len(validated.known_future_covariates) == 2


def test_covariate_cannot_exceed_horizon() -> None:
    payload = build_position_request().model_dump(mode="json")
    payload["known_future_covariates"] = [
        {"horizon_step": 2, "timestamp": "4", "values": {"draw_no": 4}}
    ]
    with pytest.raises(ValidationError, match="exceeds prediction_length"):
        build_position_request().__class__.model_validate(payload)


def test_history_identity_must_match_series_order() -> None:
    payload = build_position_request().model_dump(mode="json")
    payload["history"] = list(reversed(payload["history"]))
    with pytest.raises(ValidationError, match="exactly match series_ids"):
        build_position_request().__class__.model_validate(payload)


def test_position_and_candidate_series_counts_are_geometry_driven() -> None:
    payload = build_position_request().model_dump(mode="json")
    payload["task_formulation"] = TaskFormulation.CANDIDATE_SCORE.value
    with pytest.raises(ValidationError, match="series count does not match"):
        build_position_request().__class__.model_validate(payload)


def test_legacy_lane_requires_fixed_identity() -> None:
    payload = build_position_request().model_dump(mode="json")
    payload["revision"] = "untrusted"
    with pytest.raises(ValidationError, match="fixed repo_id and revision"):
        build_position_request().__class__.model_validate(payload)


def test_ts3_lane_remains_blocked_pending_provenance() -> None:
    manifest = lane_manifest(CheckpointLane.TS3_CURRENT)
    assert (
        manifest.execution_status
        is ExecutionStatus.BLOCKED_PENDING_CHECKPOINT_HASH_AND_LICENSE_REVIEW
    )
    assert manifest.sha256 is None
    assert manifest.production_champion_eligible is False


def _candidate_request_payload(
    *, prediction_length: int = 1, strictly_increasing: bool = True
) -> dict[str, object]:
    payload = build_position_request().model_dump(mode="json")
    candidate_min = 1 if strictly_increasing else 0
    candidate_max = 5 if strictly_increasing else 9
    selection_count = 2 if strictly_increasing else 3
    series_ids = [
        f"candidate-{candidate:02d}" for candidate in range(candidate_min, candidate_max + 1)
    ]
    payload["task_formulation"] = TaskFormulation.CANDIDATE_SCORE.value
    payload["game_geometry"] = {
        "game_id": "candidate-test",
        "position_count": selection_count,
        "candidate_min": candidate_min,
        "candidate_max": candidate_max,
        "selection_count": selection_count,
        "strictly_increasing": strictly_increasing,
    }
    payload["series_ids"] = series_ids
    payload["history"] = [
        {
            "series_id": series_id,
            "timestamps": ["1", "2", "3"],
            "values": [0.0, 1.0, 0.0],
        }
        for series_id in series_ids
    ]
    payload["prediction_length"] = prediction_length
    return payload


def test_history_timestamp_identity_must_match_across_series() -> None:
    payload = build_position_request().model_dump(mode="json")
    payload["history"][1]["timestamps"] = ["1", "different", "3"]
    with pytest.raises(ValidationError, match="identical timestamp identity"):
        build_position_request().__class__.model_validate(payload)


def test_known_future_covariates_reject_duplicate_series_horizon_rows() -> None:
    payload = build_position_request().model_dump(mode="json")
    row = {"horizon_step": 1, "timestamp": "4", "values": {"draw_no": 4}}
    payload["known_future_covariates"] = [row, row]
    with pytest.raises(ValidationError, match="unique per series/horizon"):
        build_position_request().__class__.model_validate(payload)


def test_candidate_score_requires_unique_selection_game() -> None:
    payload = _candidate_request_payload(strictly_increasing=False)
    with pytest.raises(ValidationError, match="strictly increasing unique-selection"):
        build_position_request().__class__.model_validate(payload)


def test_legacy_candidate_score_is_explicitly_one_step() -> None:
    payload = _candidate_request_payload(prediction_length=2)
    with pytest.raises(ValidationError, match="prediction_length=1 only"):
        build_position_request().__class__.model_validate(payload)

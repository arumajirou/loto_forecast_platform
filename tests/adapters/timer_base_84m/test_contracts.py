from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from loto.adapters.timer_base_84m.contracts import TimerRequest
from loto.timer_base_84m_campaign.chronology import TimeAxis, validate_chronology
from loto.timer_base_84m_campaign.geometry import Game, geometry_for


def request_payload(*, game: Game = Game.NUMBERS3, context: int = 96) -> dict:
    geometry = geometry_for(game)
    draws = tuple(range(1000, 1000 + context))
    dates = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(context))
    mapping = validate_chronology(
        game=game,
        time_axis=TimeAxis.DRAW_SEQUENCE,
        draw_numbers=draws,
        dates=dates,
        cutoff_draw_no=draws[-1],
        cutoff_date=dates[-1],
        actuals_used=False,
    )
    return {
        "schema_version": "timer-base-84m.request.v1",
        "run_id": "timer-test-0001",
        "operation": "validate_request",
        "model_id": "timer-base-84m",
        "repo_id": "thuml/timer-base-84m",
        "package_version": "4.40.1",
        "source_revision": "1ff8d1afc073182e6d46022069ff32470ab47945",
        "model_revision": "70077a71acce1b4c00d98332fcaabc694255d8e5",
        "config_sha256": "UNVERIFIED",
        "weight_sha256": "9c3d18f12ffe1ea7d4fa70eb3304b26e3841164a6a265fbae4f7a05cd213aa3d",
        "license": "Apache-2.0",
        "game": game,
        "target_layout": "position_univariate",
        "context_length": context,
        "prediction_length": 1,
        "seed": 1,
        "requested_device": "cpu",
        "input_shape": (geometry.position_count, context),
        "series": tuple(
            tuple(float(index) for index in range(context))
            for _ in range(geometry.position_count)
        ),
        "past_covariates": None,
        "known_future_covariates": None,
        "chronology_evidence": {
            "time_axis": TimeAxis.DRAW_SEQUENCE,
            "cutoff_draw_no": draws[-1],
            "cutoff_date": dates[-1],
            "draw_numbers": draws,
            "dates": dates,
            "mapping_sha256": mapping,
            "future_actuals_present": False,
            "duplicate_free": True,
            "strictly_increasing": True,
            "gap_free": True,
        },
        "actuals_used": False,
        "artifact_paths": {
            "request_path": "artifacts/request.json",
            "response_path": "artifacts/response.json",
            "snapshot_path": "snapshots/timer-base-84m",
            "manifest_path": "artifacts/manifest.json",
        },
    }


def reject(field: str, value: object) -> None:
    payload = request_payload()
    payload[field] = value
    with pytest.raises(ValidationError):
        TimerRequest.model_validate(payload)


def test_valid_contract() -> None:
    request = TimerRequest.model_validate(request_payload())
    assert request.input_shape == (3, 96)


def test_unknown_field_rejected() -> None:
    payload = request_payload()
    payload["unknown"] = 1
    with pytest.raises(ValidationError):
        TimerRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_id", "timer"),
        ("model_revision", "0" * 40),
        ("weight_sha256", "0" * 64),
        ("license", "MIT"),
        ("context_length", 95),
        ("context_length", 2881),
        ("context_length", 97),
        ("prediction_length", 3),
        ("target_layout", "multivariate"),
        ("past_covariates", {"x": [1.0]}),
        ("known_future_covariates", {"x": [1.0]}),
    ],
)
def test_invalid_fields_rejected(field: str, value: object) -> None:
    reject(field, value)


def test_wrong_game_position_count_rejected() -> None:
    payload = request_payload(game=Game.LOTO7)
    payload["series"] = payload["series"][:-1]
    with pytest.raises(ValidationError):
        TimerRequest.model_validate(payload)


def test_non_finite_input_rejected() -> None:
    payload = request_payload()
    rows = [list(row) for row in payload["series"]]
    rows[0][0] = float("nan")
    payload["series"] = tuple(tuple(row) for row in rows)
    with pytest.raises(ValidationError):
        TimerRequest.model_validate(payload)


def test_artifact_path_traversal_rejected() -> None:
    payload = request_payload()
    payload["artifact_paths"]["snapshot_path"] = "../weights"
    with pytest.raises(ValidationError):
        TimerRequest.model_validate(payload)

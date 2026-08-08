from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.adapters.moirai2.contracts import Moirai2ProviderRequest, request_v1_to_v2


def _payload(position_count: int = 5, horizon: int = 1) -> dict:
    columns = [f"n{index}" for index in range(1, position_count + 1)]
    history = [
        {column: float(row + index) for index, column in enumerate(columns)} for row in range(128)
    ]
    return {
        "run_id": "contract-test",
        "license_lane": "personal_noncommercial_research",
        "game_geometry": {
            "game_id": "test",
            "position_count": position_count,
            "candidate_min": 1,
            "candidate_max": 50,
            "strictly_increasing": True,
        },
        "series_layout": "position_multivariate",
        "position_columns": columns,
        "history": history,
        "context_length": 128,
        "prediction_length": horizon,
    }


def test_request_rejects_unknown_key() -> None:
    payload = _payload()
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        Moirai2ProviderRequest.model_validate(payload)


def test_request_accepts_arbitrary_position_count_and_formal_horizons() -> None:
    for position_count in (1, 3, 4, 5, 6, 7):
        for horizon in (1, 2, 5):
            payload = _payload(position_count, horizon)
            if position_count == 1:
                payload["series_layout"] = "position_univariate"
            request = Moirai2ProviderRequest.model_validate(payload)
            assert request.game_geometry.position_count == position_count
            assert request.prediction_length == horizon


def test_future_covariate_requires_history_plus_horizon() -> None:
    payload = _payload(horizon=2)
    payload["future_covariates"] = {"weekday": [1.0, 2.0]}
    payload["future_covariate_availability"] = {"weekday": "known_at_prediction_time"}
    with pytest.raises(ValidationError, match=r"history\+horizon"):
        Moirai2ProviderRequest.model_validate(payload)


def test_schema_v1_compatibility_is_exact_loto7_only() -> None:
    history = [{f"n{position}": float(position) for position in range(1, 8)} for _ in range(20)]
    converted = request_v1_to_v2(
        {
            "schema_version": 1,
            "model_id": "moirai",
            "repo_id": "Salesforce/moirai-2.0-R-small",
            "revision": "30f43ff08c8494f4943ae1521e9d4e94a0fbb389",
            "local_files_only": True,
            "device": "cpu",
            "dtype": "float32",
            "history": history,
            "prediction_length": 1,
        }
    )
    assert converted["schema_version"] == 2
    assert converted["model_id"] == "moirai-2.0-r-small"
    assert converted["game_geometry"]["position_count"] == 7


def test_future_covariate_requires_known_at_prediction_time_evidence() -> None:
    payload = _payload(horizon=2)
    payload["future_covariates"] = {"weekday": [1.0] * 130}
    with pytest.raises(ValidationError, match="known-at-prediction-time"):
        Moirai2ProviderRequest.model_validate(payload)
    payload["future_covariate_availability"] = {"weekday": "known_at_prediction_time"}
    request = Moirai2ProviderRequest.model_validate(payload)
    assert request.future_covariate_availability["weekday"] == "known_at_prediction_time"


def test_draw_sequence_timestamps_must_be_gap_free() -> None:
    payload = _payload(position_count=3)
    payload["timestamps"] = list(range(1, 128)) + [129]
    with pytest.raises(ValidationError, match="gap-free"):
        Moirai2ProviderRequest.model_validate(payload)


def test_request_rejects_string_bool_and_non_finite_history_values() -> None:
    for bad_value in ("1.0", True, float("nan"), float("inf")):
        payload = _payload(position_count=1)
        payload["series_layout"] = "position_univariate"
        payload["history"][0]["n1"] = bad_value
        with pytest.raises(ValidationError):
            Moirai2ProviderRequest.model_validate(payload)


def test_request_rejects_unsafe_covariate_names() -> None:
    payload = _payload()
    payload["past_covariates"] = {"../../future": [1.0] * 128}
    with pytest.raises(ValidationError, match="unsafe covariate"):
        Moirai2ProviderRequest.model_validate(payload)


def test_request_rejects_token_budget_before_runtime() -> None:
    payload = _payload(position_count=7)
    payload["context_length"] = 1200
    payload["history"] = payload["history"] * 10
    with pytest.raises(ValidationError, match="total token count"):
        Moirai2ProviderRequest.model_validate(payload)

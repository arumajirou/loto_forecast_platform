from __future__ import annotations

from copy import deepcopy

from loto.adapters.autogluon import strict_provider


def _payload() -> dict:
    return {
        "schema_version": 2,
        "provider_version": 2,
        "run_id": "strict-preflight",
        "operation": "fit_predict_save",
        "execution_mode": "explicit_single_model",
        "model_ids": ["Naive"],
        "artifact_dir": "/tmp/strict-preflight",
        "history": [
            {"draw_no": 1, "draw_date": "2026-01-01", "n1": 1, "n2": 4, "n3": 7},
            {"draw_no": 2, "draw_date": "2026-01-08", "n1": 2, "n2": 5, "n3": 8},
        ],
        "geometry": {
            "game_id": "numbers3",
            "position_columns": ["n1", "n2", "n3"],
            "candidate_min": 0,
            "candidate_max": 9,
            "selection_count": 3,
            "horizon": 1,
            "allow_duplicates": False,
            "sort_policy": "ascending",
        },
        "predictor": {"target": "target", "prediction_length": 1, "freq": "D"},
        "fit": {
            "presets": None,
            "hyperparameters": {"seasonal_period": 1},
            "enable_ensemble": False,
        },
        "requested_device": "cpu",
    }


def test_valid_request_reaches_base_provider(monkeypatch) -> None:
    marker = {"called": False}

    def fake_base(payload, *, runtime=None):
        marker["called"] = True
        return {"status": "OK", "run_id": payload["run_id"]}

    monkeypatch.setattr(strict_provider, "_run_provider_v2", fake_base)
    response = strict_provider.run_provider_v2_strict(_payload())
    assert response["status"] == "OK"
    assert marker["called"] is True


def test_non_increasing_source_order_is_rejected_before_base_provider(monkeypatch) -> None:
    payload = _payload()
    payload["history"][1]["draw_no"] = 1
    monkeypatch.setattr(
        strict_provider,
        "_run_provider_v2",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    response = strict_provider.run_provider_v2_strict(payload)
    assert response["status"] == "ERROR"
    assert response["error"]["code"] == "SOURCE_ORDER_NOT_STRICTLY_INCREASING"


def test_non_increasing_timestamp_is_rejected() -> None:
    payload = _payload()
    payload["history"][1]["draw_date"] = "2025-12-31"
    response = strict_provider.run_provider_v2_strict(payload)
    assert response["status"] == "ERROR"
    assert response["error"]["code"] == "SOURCE_TIMESTAMP_NOT_STRICTLY_INCREASING"


def test_source_order_must_be_integer() -> None:
    payload = _payload()
    payload["history"][0]["draw_no"] = "1"
    response = strict_provider.run_provider_v2_strict(payload)
    assert response["status"] == "ERROR"
    assert response["error"]["code"] == "SOURCE_ORDER_TYPE_INVALID"


def test_frequency_and_target_mismatches_fail_closed() -> None:
    frequency = deepcopy(_payload())
    frequency["predictor"]["freq"] = "W"
    response = strict_provider.run_provider_v2_strict(frequency)
    assert response["error"]["code"] == "TIMELINE_FREQUENCY_MISMATCH"

    target = deepcopy(_payload())
    target["predictor"]["target"] = "y"
    response = strict_provider.run_provider_v2_strict(target)
    assert response["error"]["code"] == "TARGET_COLUMN_NOT_IMPLEMENTED"

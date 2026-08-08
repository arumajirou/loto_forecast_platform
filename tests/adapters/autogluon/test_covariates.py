from __future__ import annotations

import json

import pytest

from loto.adapters.autogluon.covariates import (
    CovariateContractError,
    ProviderRequestV2Covariates,
    compile_covariates,
    has_covariate_payload,
    persist_covariate_context,
    to_known_covariates_data_frame,
    to_time_series_data_frame,
    validate_saved_covariate_context,
)


def _payload() -> dict:
    return {
        "schema_version": 2,
        "provider_version": 2,
        "run_id": "p13-covariates",
        "operation": "fit_predict_save",
        "execution_mode": "explicit_single_model",
        "model_ids": ["Naive"],
        "artifact_dir": "/tmp/p13-covariates",
        "history": [
            {
                "draw_no": 1,
                "draw_date": "2026-01-01",
                "n1": 1,
                "n2": 4,
                "n3": 7,
                "holiday": 0,
                "rain": 1.5,
            },
            {
                "draw_no": 2,
                "draw_date": "2026-01-08",
                "n1": 2,
                "n2": 5,
                "n3": 8,
                "holiday": 1,
                "rain": 0.0,
            },
        ],
        "geometry": {
            "game_id": "numbers3",
            "position_columns": ["n1", "n2", "n3"],
            "candidate_min": 0,
            "candidate_max": 9,
            "selection_count": 3,
            "horizon": 2,
            "allow_duplicates": False,
            "sort_policy": "ascending",
        },
        "predictor": {
            "target": "target",
            "known_covariates_names": ["holiday"],
            "prediction_length": 2,
            "freq": "D",
            "eval_metric": "MAE",
            "quantile_levels": [0.1, 0.5, 0.9],
            "cache_predictions": True,
        },
        "fit": {},
        "covariates": {
            "past_covariates_names": ["rain"],
            "static_feature_names": ["position_group"],
            "future_known_covariates": [
                {"horizon_step": 1, "holiday": 0},
                {"horizon_step": 2, "holiday": 1},
            ],
            "static_features": [
                {"item_id": "position-1", "position_group": "low"},
                {"item_id": "position-2", "position_group": "mid"},
                {"item_id": "position-3", "position_group": "high"},
            ],
        },
        "seed": 1,
        "requested_device": "cpu",
    }


def _compiled():
    request = ProviderRequestV2Covariates.model_validate(_payload())
    return compile_covariates(request)


def test_detects_covariate_payload() -> None:
    assert has_covariate_payload(_payload())


def test_compiles_known_past_and_static_covariates() -> None:
    compiled = _compiled()
    assert len(compiled.records) == 6
    assert len(compiled.future_known_records) == 6
    assert len(compiled.static_feature_records) == 3
    assert compiled.records[0]["holiday"] == 0
    assert compiled.records[0]["rain"] == 1.5


def test_future_timestamps_follow_compiled_history() -> None:
    first = _compiled().future_known_records[0]
    assert first["timestamp"].startswith("2000-01-03")


def test_covariate_role_overlap_is_rejected() -> None:
    payload = _payload()
    payload["covariates"]["past_covariates_names"] = ["holiday"]
    request = ProviderRequestV2Covariates.model_validate(payload)
    with pytest.raises(CovariateContractError) as exc_info:
        compile_covariates(request)
    assert exc_info.value.code == "COVARIATE_ROLE_OVERLAP"


def test_missing_history_covariate_is_rejected() -> None:
    payload = _payload()
    del payload["history"][1]["rain"]
    request = ProviderRequestV2Covariates.model_validate(payload)
    with pytest.raises(CovariateContractError) as exc_info:
        compile_covariates(request)
    assert exc_info.value.code == "HISTORY_COVARIATE_MISSING"


def test_future_horizon_mismatch_is_rejected() -> None:
    payload = _payload()
    payload["covariates"]["future_known_covariates"] = [{"horizon_step": 1, "holiday": 0}]
    request = ProviderRequestV2Covariates.model_validate(payload)
    with pytest.raises(CovariateContractError) as exc_info:
        compile_covariates(request)
    assert exc_info.value.code == "FUTURE_KNOWN_HORIZON_MISMATCH"


def test_future_unknown_column_is_rejected() -> None:
    payload = _payload()
    payload["covariates"]["future_known_covariates"][0]["rain"] = 3
    request = ProviderRequestV2Covariates.model_validate(payload)
    with pytest.raises(CovariateContractError) as exc_info:
        compile_covariates(request)
    assert exc_info.value.code == "FUTURE_KNOWN_SCHEMA_MISMATCH"


def test_static_item_mismatch_is_rejected() -> None:
    payload = _payload()
    payload["covariates"]["static_features"][0]["item_id"] = "position-9"
    request = ProviderRequestV2Covariates.model_validate(payload)
    with pytest.raises(CovariateContractError) as exc_info:
        compile_covariates(request)
    assert exc_info.value.code == "STATIC_FEATURE_ITEM_MISMATCH"


def test_nonfinite_covariate_is_rejected() -> None:
    payload = _payload()
    payload["history"][0]["rain"] = float("nan")
    request = ProviderRequestV2Covariates.model_validate(payload)
    with pytest.raises(CovariateContractError) as exc_info:
        compile_covariates(request)
    assert exc_info.value.code == "COVARIATE_VALUE_NOT_FINITE"


class _FakeTimeSeriesDataFrame:
    calls: list[tuple[object, dict]] = []

    @classmethod
    def from_data_frame(cls, frame, **kwargs):
        cls.calls.append((frame.copy(), kwargs.copy()))
        return {"frame": frame, "kwargs": kwargs}


class _Runtime:
    time_series_data_frame_class = _FakeTimeSeriesDataFrame


def test_dataframe_conversion_keeps_static_and_dynamic_features() -> None:
    _FakeTimeSeriesDataFrame.calls = []
    compiled = _compiled()
    to_time_series_data_frame(compiled, _Runtime())
    to_known_covariates_data_frame(compiled, _Runtime())
    train, train_kwargs = _FakeTimeSeriesDataFrame.calls[0]
    future, _future_kwargs = _FakeTimeSeriesDataFrame.calls[1]
    assert list(train.columns) == ["item_id", "timestamp", "target", "holiday", "rain"]
    assert list(train_kwargs["static_features_df"].columns) == [
        "item_id",
        "position_group",
    ]
    assert list(future.columns) == ["item_id", "timestamp", "holiday"]


def test_covariate_context_roundtrip_and_tamper_detection(tmp_path) -> None:
    compiled = _compiled()
    persist_covariate_context(tmp_path, compiled)
    assert validate_saved_covariate_context(tmp_path, compiled).endswith(".json")
    path = tmp_path / "loto_covariate_context_v2.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["static_features_sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CovariateContractError) as exc_info:
        validate_saved_covariate_context(tmp_path, compiled)
    assert exc_info.value.code == "COVARIATE_CONTEXT_MISMATCH"

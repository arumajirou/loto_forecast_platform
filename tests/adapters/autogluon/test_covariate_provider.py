from __future__ import annotations

from pathlib import Path

import pandas as pd

from loto.adapters.autogluon.covariate_provider import run_provider_v2_covariates
from loto.adapters.autogluon.provider import ProviderRuntime
from loto.adapters.autogluon.strict_provider import run_provider_v2_strict


class _FakeTimeSeriesDataFrame:
    @classmethod
    def from_data_frame(cls, frame, **kwargs):
        return {"frame": frame, "kwargs": kwargs}


class _FakePredictor:
    last = None
    model_name = "Naive"

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.fit_args = None
        self.predict_args = None
        self.model_best = type(self).model_name
        _FakePredictor.last = self

    def fit(self, data, **kwargs):
        self.fit_args = (data, kwargs)
        Path(self.kwargs["path"]).mkdir(parents=True, exist_ok=True)
        return self

    def predict(self, data, **kwargs):
        self.predict_args = (data, kwargs)
        rows = []
        for item_id in ("position-1", "position-2", "position-3"):
            for offset in range(2):
                rows.append(
                    {
                        "item_id": item_id,
                        "timestamp": pd.Timestamp("2000-01-03") + pd.Timedelta(days=offset),
                        "mean": 5.0,
                        "0.1": 4.0,
                        "0.5": 5.0,
                        "0.9": 6.0,
                    }
                )
        return pd.DataFrame(rows).set_index(["item_id", "timestamp"])

    def model_names(self):
        return [type(self).model_name]

    @classmethod
    def load(cls, path):
        return cls(path=path)


def _payload(tmp_path) -> dict:
    return {
        "schema_version": 2,
        "provider_version": 2,
        "run_id": "p13-provider",
        "operation": "fit_predict_save",
        "execution_mode": "explicit_single_model",
        "model_ids": ["Naive"],
        "artifact_dir": str(tmp_path / "artifact"),
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


def _runtime() -> ProviderRuntime:
    return ProviderRuntime(
        predictor_class=_FakePredictor,
        time_series_data_frame_class=_FakeTimeSeriesDataFrame,
        cuda_available=False,
        library_version="1.5.0",
    )


def test_fit_predict_passes_known_covariates_and_static_features(tmp_path) -> None:
    response = run_provider_v2_covariates(_payload(tmp_path), runtime=_runtime())
    assert response["status"] == "OK"
    assert len(response["predictions"]) == 6
    assert "known_covariates" in _FakePredictor.last.predict_args[1]
    static_frame = _FakePredictor.last.fit_args[0]["kwargs"]["static_features_df"]
    assert static_frame.shape == (3, 2)
    assert response["metadata"]["known_covariate_names"] == ["holiday"]
    assert Path(response["artifacts"]["covariate_context"]).is_file()


def test_missing_future_values_fail_before_runtime(tmp_path) -> None:
    payload = _payload(tmp_path)
    payload["covariates"]["future_known_covariates"] = []
    response = run_provider_v2_covariates(payload, runtime=_runtime())
    assert response["status"] == "ERROR"
    assert response["error"]["code"] == "FUTURE_KNOWN_HORIZON_MISMATCH"


def test_strict_router_dispatches_covariate_payload(tmp_path, monkeypatch) -> None:
    payload = _payload(tmp_path)
    payload["model_ids"] = ["TemporalFusionTransformer"]
    monkeypatch.setattr(_FakePredictor, "model_name", "TemporalFusionTransformer")
    response = run_provider_v2_strict(payload, runtime=_runtime())
    assert response["status"] == "OK"
    decision = response["metadata"]["covariate_capability_decision"]
    assert decision["selected_model_ids"] == ["TemporalFusionTransformer"]


def test_strict_router_preserves_non_covariate_base_path(tmp_path, monkeypatch) -> None:
    payload = _payload(tmp_path)
    payload["predictor"]["known_covariates_names"] = []
    payload["covariates"] = {
        "past_covariates_names": [],
        "static_feature_names": [],
        "future_known_covariates": [],
    }
    monkeypatch.setattr(
        "loto.adapters.autogluon.strict_provider._run_provider_v2",
        lambda request, runtime=None: {"status": "BASE_PATH"},
    )
    response = run_provider_v2_strict(payload, runtime=_runtime())
    assert response["status"] == "BASE_PATH"

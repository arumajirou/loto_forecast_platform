from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from loto.adapters.autogluon.provider import ProviderRuntime, run_provider_v2


class FakeTimeSeriesDataFrame:
    captured_frame: pd.DataFrame | None = None

    @classmethod
    def from_data_frame(cls, frame, *, id_column, timestamp_column):
        assert id_column == "item_id"
        assert timestamp_column == "timestamp"
        cls.captured_frame = frame.copy()
        return frame.copy()


class FakePredictor:
    instances: list["FakePredictor"] = []
    loaded_paths: list[str] = []
    prediction_horizon = 2
    prediction_items = ("position-1", "position-2", "position-3")
    bad_shape = False

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.fit_kwargs = None
        self.model_best = "Naive"
        type(self).instances.append(self)

    @classmethod
    def load(cls, path: str):
        cls.loaded_paths.append(path)
        return cls(path=path)

    def fit(self, data, **kwargs):
        self.fit_data = data
        self.fit_kwargs = kwargs
        Path(self.init_kwargs["path"]).joinpath("predictor.marker").write_text(
            "saved\n", encoding="utf-8"
        )
        return self

    def predict(self, data):
        items = self.prediction_items
        horizon = self.prediction_horizon
        if self.bad_shape:
            items = items[:-1]
        rows = []
        for item_index, item_id in enumerate(items, start=1):
            for step in range(horizon):
                rows.append(
                    {
                        "item_id": item_id,
                        "timestamp": pd.Timestamp("2030-01-01") + pd.Timedelta(days=step),
                        "mean": float(item_index + step),
                        "0.1": float(item_index + step - 0.5),
                        "0.5": float(item_index + step),
                        "0.9": float(item_index + step + 0.5),
                    }
                )
        return pd.DataFrame(rows).set_index(["item_id", "timestamp"])

    def model_names(self):
        return ["Naive"]


def _runtime() -> ProviderRuntime:
    return ProviderRuntime(
        predictor_class=FakePredictor,
        time_series_data_frame_class=FakeTimeSeriesDataFrame,
        cuda_available=False,
        library_version="1.5.0",
    )


def _payload(artifact_dir: Path, *, operation: str = "fit_predict_save") -> dict:
    return {
        "schema_version": 2,
        "provider_version": 2,
        "run_id": "p4-provider-test",
        "operation": operation,
        "execution_mode": "explicit_single_model",
        "model_ids": ["Naive"],
        "artifact_dir": str(artifact_dir),
        "history": [
            {
                "draw_no": 10,
                "draw_date": "2026-01-01",
                "n1": 1,
                "n2": 2,
                "n3": 3,
            },
            {
                "draw_no": 11,
                "draw_date": "2026-01-08",
                "n1": 2,
                "n2": 3,
                "n3": 4,
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
            "sort_policy": "preserve",
            "timeline": {
                "mode": "synthetic_regular",
                "frequency": "D",
                "base_timestamp": "2000-01-01T00:00:00+00:00",
                "source_order_field": "draw_no",
                "source_timestamp_field": "draw_date",
            },
        },
        "predictor": {
            "target": "target",
            "known_covariates_names": [],
            "prediction_length": 2,
            "freq": "D",
            "eval_metric": "MAE",
            "eval_metric_seasonal_period": None,
            "horizon_weight": [1.0, 0.5],
            "quantile_levels": [0.1, 0.5, 0.9],
            "cache_predictions": True,
        },
        "fit": {
            "time_limit_seconds": 30,
            "presets": "fast_training",
            "hyperparameters": {"seasonal_period": 1},
            "hyperparameter_tune_kwargs": None,
            "excluded_model_types": [],
            "ensemble_hyperparameters": None,
            "num_val_windows": 1,
            "val_step_size": None,
            "refit_every_n_windows": 1,
            "refit_full": False,
            "enable_ensemble": True,
            "skip_model_selection": False,
        },
        "covariates": {
            "past_covariates_names": [],
            "static_feature_names": [],
            "future_known_covariates": [],
        },
        "seed": 1,
        "requested_device": "cpu",
    }


def setup_function() -> None:
    FakePredictor.instances.clear()
    FakePredictor.loaded_paths.clear()
    FakePredictor.prediction_horizon = 2
    FakePredictor.prediction_items = ("position-1", "position-2", "position-3")
    FakePredictor.bad_shape = False


def test_fit_predict_save_executes_explicit_model_and_persists_contract(tmp_path) -> None:
    artifact_dir = tmp_path / "artifact"
    response = run_provider_v2(_payload(artifact_dir), runtime=_runtime())

    assert response["status"] == "OK"
    assert response["schema_version"] == 2
    assert response["provider_version"] == 2
    assert len(response["predictions"]) == 6
    assert response["predictions"][0]["quantiles"] == {
        "0.1": 0.5,
        "0.5": 1.0,
        "0.9": 1.5,
    }
    assert response["metadata"]["prediction_shape"] == [3, 2]
    assert response["metadata"]["finite"] is True
    assert response["runtime_evidence"]["evidence_status"] == "PARTIAL"

    predictor = FakePredictor.instances[0]
    assert predictor.init_kwargs["prediction_length"] == 2
    assert predictor.init_kwargs["horizon_weight"] == [1.0, 0.5]
    assert predictor.fit_kwargs["hyperparameters"] == {
        "Naive": {"seasonal_period": 1}
    }
    assert "presets" not in predictor.fit_kwargs
    assert predictor.fit_kwargs["enable_ensemble"] is False
    assert predictor.fit_kwargs["random_seed"] == 1

    context_path = artifact_dir / "loto_provider_context_v2.json"
    plan_path = artifact_dir / "loto_execution_plan_v2.json"
    mapping_path = artifact_dir / "loto_timeline_mapping_v2.json"
    assert context_path.exists()
    assert plan_path.exists()
    assert mapping_path.exists()
    context = json.loads(context_path.read_text(encoding="utf-8"))
    assert len(context["request_sha256"]) == 64
    assert len(context["timeline_mapping_sha256"]) == 64
    assert len(context["geometry_sha256"]) == 64


def test_load_predict_uses_saved_predictor(tmp_path) -> None:
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    (artifact_dir / "predictor.marker").write_text("saved\n", encoding="utf-8")
    response = run_provider_v2(
        _payload(artifact_dir, operation="load_predict"),
        runtime=_runtime(),
    )
    assert response["status"] == "OK"
    assert FakePredictor.loaded_paths == [str(artifact_dir)]
    assert len(response["predictions"]) == 6


def test_nonempty_artifact_directory_is_rejected_for_fit(tmp_path) -> None:
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    (artifact_dir / "existing.txt").write_text("do not overwrite", encoding="utf-8")
    response = run_provider_v2(_payload(artifact_dir), runtime=_runtime())
    assert response["status"] == "ERROR"
    assert response["error"]["code"] == "ARTIFACT_DIR_NOT_EMPTY"


def test_prediction_shape_mismatch_fails_closed(tmp_path) -> None:
    FakePredictor.bad_shape = True
    response = run_provider_v2(_payload(tmp_path / "artifact"), runtime=_runtime())
    assert response["status"] == "ERROR"
    assert response["error"]["code"] == "PREDICTION_CONTRACT_FAILED"


def test_covariates_are_rejected_in_p4_instead_of_silently_dropped(tmp_path) -> None:
    payload = _payload(tmp_path / "artifact")
    payload["predictor"]["known_covariates_names"] = ["holiday"]
    response = run_provider_v2(payload, runtime=_runtime())
    assert response["status"] == "ERROR"
    assert response["error"]["code"] == "KNOWN_COVARIATES_NOT_IMPLEMENTED_P4"


def test_unknown_request_field_is_rejected_by_pydantic_contract(tmp_path) -> None:
    payload = _payload(tmp_path / "artifact")
    payload["silently_ignored"] = True
    response = run_provider_v2(payload, runtime=_runtime())
    assert response["status"] == "ERROR"
    assert response["error"]["code"] == "CONTRACT_VALIDATION_FAILED"


def test_quantile_column_mismatch_fails_closed(tmp_path, monkeypatch) -> None:
    original_predict = FakePredictor.predict

    def predict_without_all_quantiles(self, data):
        frame = original_predict(self, data).reset_index()
        return frame.drop(columns=["0.9"]).set_index(["item_id", "timestamp"])

    monkeypatch.setattr(FakePredictor, "predict", predict_without_all_quantiles)
    response = run_provider_v2(_payload(tmp_path / "artifact"), runtime=_runtime())
    assert response["status"] == "ERROR"
    assert response["error"]["code"] == "PREDICTION_CONTRACT_FAILED"

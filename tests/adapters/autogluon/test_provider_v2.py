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
    saved_model_names: dict[str, list[str]] = {}
    prediction_horizon = 2
    prediction_items = ("position-1", "position-2", "position-3")
    bad_shape = False
    last_predict_seed: int | None = None
    loaded_model_names_override: list[str] | None = None

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.fit_kwargs = None
        self._model_names = ["Naive"]
        self.model_best = "Naive"
        type(self).instances.append(self)

    @classmethod
    def load(cls, path: str):
        cls.loaded_paths.append(path)
        predictor = cls(path=path)
        predictor._model_names = list(
            cls.loaded_model_names_override
            if cls.loaded_model_names_override is not None
            else cls.saved_model_names[path]
        )
        predictor.model_best = predictor._model_names[0]
        return predictor

    def fit(self, data, **kwargs):
        self.fit_data = data
        self.fit_kwargs = kwargs
        model_name = next(iter(kwargs["hyperparameters"]))
        self._model_names = [model_name]
        self.model_best = model_name
        artifact = Path(self.init_kwargs["path"])
        artifact.joinpath("predictor.marker").write_text("saved\n", encoding="utf-8")
        type(self).saved_model_names[str(artifact)] = list(self._model_names)
        return self

    def predict(self, data, *, random_seed):
        type(self).last_predict_seed = random_seed
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
        return list(self._model_names)


def _runtime(*, version: str = "1.5.0") -> ProviderRuntime:
    return ProviderRuntime(
        predictor_class=FakePredictor,
        time_series_data_frame_class=FakeTimeSeriesDataFrame,
        cuda_available=False,
        library_version=version,
    )


def _payload(
    artifact_dir: Path,
    *,
    operation: str = "fit_predict_save",
    model_id: str = "Naive",
) -> dict:
    return {
        "schema_version": 2,
        "provider_version": 2,
        "run_id": "p4-provider-test",
        "operation": operation,
        "execution_mode": "explicit_single_model",
        "model_ids": [model_id],
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
    FakePredictor.saved_model_names.clear()
    FakePredictor.prediction_horizon = 2
    FakePredictor.prediction_items = ("position-1", "position-2", "position-3")
    FakePredictor.bad_shape = False
    FakePredictor.last_predict_seed = None
    FakePredictor.loaded_model_names_override = None


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
    assert response["metadata"]["model_identity_verified"] is True
    assert response["metadata"]["prediction_random_seed"] == 1
    assert response["runtime_evidence"]["evidence_status"] == "PARTIAL"
    assert FakePredictor.last_predict_seed == 1

    predictor = FakePredictor.instances[0]
    assert predictor.init_kwargs["prediction_length"] == 2
    assert predictor.init_kwargs["horizon_weight"] == [1.0, 0.5]
    assert predictor.fit_kwargs["hyperparameters"] == {"Naive": {"seasonal_period": 1}}
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
    assert context["runtime_snapshot"]["library_version"] == "1.5.0"
    assert context["runtime_snapshot"]["model_identity"]["verified"] is True


def test_load_predict_uses_saved_predictor_without_overwriting_context(tmp_path) -> None:
    artifact_dir = tmp_path / "artifact"
    fit_response = run_provider_v2(_payload(artifact_dir), runtime=_runtime())
    assert fit_response["status"] == "OK"
    context_path = artifact_dir / "loto_provider_context_v2.json"
    original_context = context_path.read_bytes()

    response = run_provider_v2(
        _payload(artifact_dir, operation="load_predict"),
        runtime=_runtime(),
    )
    assert response["status"] == "OK"
    assert FakePredictor.loaded_paths == [str(artifact_dir)]
    assert len(response["predictions"]) == 6
    assert context_path.read_bytes() == original_context
    assert (
        response["metadata"]["saved_context_sha256"]
        == fit_response["metadata"]["saved_context_sha256"]
    )


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

    def predict_without_all_quantiles(self, data, *, random_seed):
        frame = original_predict(self, data, random_seed=random_seed).reset_index()
        return frame.drop(columns=["0.9"]).set_index(["item_id", "timestamp"])

    monkeypatch.setattr(FakePredictor, "predict", predict_without_all_quantiles)
    response = run_provider_v2(_payload(tmp_path / "artifact"), runtime=_runtime())
    assert response["status"] == "ERROR"
    assert response["error"]["code"] == "PREDICTION_CONTRACT_FAILED"


def test_load_rejects_different_requested_model_before_pickle_load(tmp_path) -> None:
    artifact_dir = tmp_path / "artifact"
    assert run_provider_v2(_payload(artifact_dir), runtime=_runtime())["status"] == "OK"
    response = run_provider_v2(
        _payload(artifact_dir, operation="load_predict", model_id="Theta"),
        runtime=_runtime(),
    )
    assert response["status"] == "ERROR"
    assert response["error"]["code"] == "ARTIFACT_MODEL_ID_MISMATCH"
    assert FakePredictor.loaded_paths == []


def test_load_rejects_tampered_plan_before_pickle_load(tmp_path) -> None:
    artifact_dir = tmp_path / "artifact"
    assert run_provider_v2(_payload(artifact_dir), runtime=_runtime())["status"] == "OK"
    plan_path = artifact_dir / "loto_execution_plan_v2.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["selected_model_ids"] = ["Theta"]
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    response = run_provider_v2(
        _payload(artifact_dir, operation="load_predict"),
        runtime=_runtime(),
    )
    assert response["status"] == "ERROR"
    assert response["error"]["code"] == "ARTIFACT_CONTEXT_PLAN_MISMATCH"
    assert FakePredictor.loaded_paths == []


def test_runtime_version_mismatch_fails_before_fit(tmp_path) -> None:
    response = run_provider_v2(
        _payload(tmp_path / "artifact"),
        runtime=_runtime(version="1.4.0"),
    )
    assert response["status"] == "ERROR"
    assert response["error"]["code"] == "RUNTIME_VERSION_MISMATCH"


def test_loaded_model_names_must_match_saved_snapshot(tmp_path) -> None:
    artifact_dir = tmp_path / "artifact"
    assert run_provider_v2(_payload(artifact_dir), runtime=_runtime())["status"] == "OK"
    FakePredictor.loaded_model_names_override = ["Theta"]
    response = run_provider_v2(
        _payload(artifact_dir, operation="load_predict"),
        runtime=_runtime(),
    )
    assert response["status"] == "ERROR"
    assert response["error"]["code"] == "MODEL_IDENTITY_NOT_VERIFIED"

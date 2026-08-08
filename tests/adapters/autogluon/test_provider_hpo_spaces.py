from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pandas as pd

from loto.adapters.autogluon.provider import ProviderRuntime, run_provider_v2


class FakeTimeSeriesDataFrame:
    @classmethod
    def from_data_frame(cls, frame, **_kwargs):
        return frame


class SpaceConstructor:
    def __init__(self, name: str):
        self.name = name

    def __call__(self, *args, **kwargs):
        return {"space": self.name, "args": args, "kwargs": kwargs}


class FakePredictor:
    fit_kwargs = None

    def __init__(self, **kwargs):
        self.path = kwargs["path"]

    def fit(self, _time_series, **kwargs):
        type(self).fit_kwargs = kwargs
        from pathlib import Path

        Path(self.path, "model.txt").write_text("fake\n", encoding="utf-8")

    def predict(self, _time_series):
        rows = []
        for index in range(1, 4):
            rows.append(
                {
                    "item_id": f"position-{index}",
                    "timestamp": pd.Timestamp("2026-02-01"),
                    "mean": float(index),
                    "0.1": float(index),
                    "0.5": float(index),
                    "0.9": float(index),
                }
            )
        return pd.DataFrame(rows).set_index(["item_id", "timestamp"])

    def model_names(self):
        return ["SeasonalNaive"]

    @property
    def model_best(self):
        return "SeasonalNaive"


def _request(tmp_path, *, execution_mode="hpo_single_model"):
    hyperparameters = {
        "SeasonalNaive": {
            "seasonal_period": {
                "__space__": "categorical",
                "choices": [1, 2],
            }
        }
    }
    return {
        "schema_version": 2,
        "provider_version": 2,
        "run_id": "hpo-space-test",
        "operation": "fit_predict_save",
        "execution_mode": execution_mode,
        "model_ids": ["SeasonalNaive"],
        "artifact_dir": str(tmp_path / "artifact"),
        "history": [
            {
                "draw_no": index,
                "draw_date": f"2026-01-{index:02d}",
                "n1": 1,
                "n2": 4,
                "n3": 7,
            }
            for index in range(1, 13)
        ],
        "geometry": {
            "game_id": "numbers3",
            "position_columns": ["n1", "n2", "n3"],
            "candidate_min": 0,
            "candidate_max": 9,
            "selection_count": 3,
            "horizon": 1,
            "sort_policy": "ascending",
        },
        "predictor": {
            "prediction_length": 1,
            "quantile_levels": [0.1, 0.5, 0.9],
        },
        "fit": {
            "presets": None,
            "hyperparameters": hyperparameters,
            "hyperparameter_tune_kwargs": {"num_trials": 2},
            "enable_ensemble": False,
        },
        "seed": 1,
        "requested_device": "cpu",
    }


def _runtime():
    return ProviderRuntime(
        predictor_class=FakePredictor,
        time_series_data_frame_class=FakeTimeSeriesDataFrame,
        cuda_available=False,
        library_version="1.5.0",
    )


def test_hpo_descriptor_is_materialized_inside_provider(monkeypatch, tmp_path) -> None:
    common = ModuleType("autogluon.common")
    common.space = SimpleNamespace(
        Categorical=SpaceConstructor("Categorical"),
        Int=SpaceConstructor("Int"),
        Real=SpaceConstructor("Real"),
    )
    package = ModuleType("autogluon")
    package.common = common
    monkeypatch.setitem(sys.modules, "autogluon", package)
    monkeypatch.setitem(sys.modules, "autogluon.common", common)

    response = run_provider_v2(_request(tmp_path), runtime=_runtime())

    assert response["status"] == "OK"
    descriptor = FakePredictor.fit_kwargs["hyperparameters"]["SeasonalNaive"]["seasonal_period"]
    assert descriptor["space"] == "Categorical"
    assert descriptor["args"] == (1, 2)


def test_non_hpo_mode_rejects_search_space_before_runtime(tmp_path) -> None:
    request = _request(tmp_path, execution_mode="explicit_single_model")
    request["fit"]["hyperparameter_tune_kwargs"] = None

    response = run_provider_v2(request, runtime=_runtime())

    assert response["status"] == "ERROR"
    assert response["error"]["code"] == "SEARCH_SPACE_WITHOUT_HPO_MODE"

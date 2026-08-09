from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from loto.darts_campaign.executor import execute_fit_predict
from loto.darts_campaign.protocol import DartsRequest


class FakeTimeSeries:
    def __init__(self, values):
        self._values = np.asarray(values, dtype=float)

    @classmethod
    def from_series(cls, series):
        return cls(series.to_numpy())

    def values(self):
        return self._values.reshape(-1, 1)


class NaiveDrift:
    def fit(self, series):
        self.series = series
        return self

    def predict(self, n):
        return FakeTimeSeries([self.series._values[-1]] * n)


class ExponentialSmoothing(NaiveDrift):
    pass


class RegressionEnsembleModel:
    def __init__(self, forecasting_models, regression_train_n_points=5):
        self.forecasting_models = forecasting_models
        self.regression_train_n_points = regression_train_n_points

    def fit(self, series):
        self.series = series
        for model in self.forecasting_models:
            model.fit(series)
        return self

    def predict(self, n):
        values = [model.predict(n)._values for model in self.forecasting_models]
        return FakeTimeSeries(np.mean(values, axis=0))


def test_current_ensemble_route_is_reproducible(tmp_path) -> None:
    frame = pd.DataFrame(
        {
            "draw_no": [1, 2, 3, 4, 5, 6],
            "n1": [1, 2, 3, 4, 5, 6],
            "n2": [2, 3, 4, 5, 6, 7],
            "n3": [3, 4, 5, 6, 7, 8],
            "n4": [4, 5, 6, 7, 8, 9],
        }
    )
    request = DartsRequest.model_validate(
        {
            "run_id": "run-1",
            "mode": "fit_predict",
            "geometry": {
                "game_id": "numbers4",
                "positions": 4,
                "min_value": 0,
                "max_value": 9,
            },
            "model": {
                "public_name": "RegressionEnsembleModel",
                "wrapper_name": "RegressionEnsembleModel",
                "base_models": ["NaiveDrift", "ExponentialSmoothing"],
            },
            "model_args": {"regression_train_n_points": 3},
            "horizon": 1,
            "artifact_dir": tmp_path,
        }
    )
    module = SimpleNamespace(
        RegressionEnsembleModel=RegressionEnsembleModel,
        NaiveDrift=NaiveDrift,
        ExponentialSmoothing=ExponentialSmoothing,
    )
    predictions, ledger, metadata, metrics, baselines, certification, seal = execute_fit_predict(
        request,
        frame,
        models_module=module,
        timeseries_cls=FakeTimeSeries,
    )
    assert predictions == [[6.0], [7.0], [8.0], [9.0]]
    assert all(row["status"] == "ACCEPTED" for row in ledger)
    assert metadata["base_models"] == ["ExponentialSmoothing", "NaiveDrift"]
    assert metrics is None
    assert baselines is None
    assert certification is None
    assert seal is None

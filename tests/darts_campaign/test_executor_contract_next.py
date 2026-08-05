from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from loto.darts_campaign.executor import execute_fit_predict
from loto.darts_campaign.protocol import DartsRequest


class FakeSeries:
    def __init__(self, values):
        self.values_array = np.asarray(values, dtype=float)

    @classmethod
    def from_series(cls, series):
        return cls(series.to_numpy(float))


class FakePrediction:
    def __init__(self, values):
        self._values = np.asarray(values, dtype=float)

    def values(self):
        return self._values


class FakeModel:
    trained_lengths: list[int] = []

    def __init__(self):
        self.last = 0.0

    def fit(self, series):
        self.last = float(series.values_array[-1])
        self.trained_lengths.append(len(series.values_array))
        return self

    def predict(self, horizon):
        return FakePrediction([self.last] * horizon)

    def save(self, path):
        from pathlib import Path

        Path(path).write_text(str(self.last), encoding="utf-8")

    @classmethod
    def load(cls, path):
        from pathlib import Path

        model = cls()
        model.last = float(Path(path).read_text(encoding="utf-8"))
        return model


def test_evaluation_is_train_only_and_roundtrip_certified(tmp_path) -> None:
    FakeModel.trained_lengths.clear()
    frame = pd.DataFrame(
        {
            "draw_no": [1, 2, 3, 4],
            "n1": [1, 2, 3, 4],
            "n2": [5, 6, 7, 8],
        }
    )
    request = DartsRequest.model_validate(
        {
            "run_id": "eval-1",
            "mode": "fit_predict",
            "geometry": {
                "game_id": "numbers2",
                "positions": 2,
                "min_value": 0,
                "max_value": 9,
            },
            "model": {"public_name": "FakeModel"},
            "horizon": 1,
            "artifact_dir": tmp_path,
            "evaluation": {"enabled": True, "holdout_size": 1},
            "persistence": {"save_model": True, "verify_save_load": True},
        }
    )
    module = SimpleNamespace(FakeModel=FakeModel)
    result = execute_fit_predict(
        request,
        frame,
        models_module=module,
        timeseries_cls=FakeSeries,
    )
    predictions, _ledger, metadata, metrics, baselines, certification, seal = result
    assert FakeModel.trained_lengths == [3, 3]
    assert predictions == [[3.0], [7.0]]
    assert metadata["holdout_rows"] == 1
    assert metrics is not None and metrics["hit_at_plus_minus_1"] == 1.0
    assert baselines is not None and "last" in baselines
    assert certification is not None
    assert {item["status"] for item in certification} == {"RUNTIME_CERTIFIED"}
    assert seal is None

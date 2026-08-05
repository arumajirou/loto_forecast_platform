from __future__ import annotations

import numpy as np
import pandas as pd

from loto.models.catalog import get_model_spec
from loto.models.workers import PositionSeriesWorker


def _history(rows: int = 12) -> pd.DataFrame:
    data: list[dict[str, object]] = []
    for index in range(rows):
        data.append(
            {
                "draw_no": index + 1,
                "draw_date": pd.Timestamp("2026-01-01")
                + pd.to_timedelta(index * 7, unit="D"),
                **{f"n{position}": position for position in range(1, 8)},
            }
        )
    return pd.DataFrame(data)


def test_autohint_bounds_val_check_steps_to_max_steps(monkeypatch) -> None:
    import neuralforecast
    import neuralforecast.losses.pytorch
    import neuralforecast.models

    captured: dict[str, object] = {}

    class FakeDistributionLoss:
        def __init__(self, **kwargs):
            captured["loss_kwargs"] = kwargs

    class FakeDLinear:
        def __init__(self, **kwargs):
            captured["base_model_config"] = kwargs

    class FakeHINT:
        def __init__(self, **kwargs):
            captured["hint_kwargs"] = kwargs

    class FakeNeuralForecast:
        def __init__(self, models, freq):
            captured["models"] = models
            captured["freq"] = freq

        def fit(self, df, val_size):
            captured["fit_rows"] = len(df)
            captured["val_size"] = val_size
            return self

        def predict(self, random_seed):
            captured["prediction_seed"] = random_seed
            values = np.arange(1, 8, dtype=float)
            return pd.DataFrame(
                {
                    "unique_id": [
                        "00-total",
                        *[f"{position:02d}-position-{position}" for position in range(1, 8)],
                    ],
                    "ds": pd.Timestamp("2026-04-01"),
                    "HINT": [float(values.sum()), *values.tolist()],
                }
            )

    monkeypatch.setattr(neuralforecast, "NeuralForecast", FakeNeuralForecast)
    monkeypatch.setattr(
        neuralforecast.losses.pytorch,
        "DistributionLoss",
        FakeDistributionLoss,
    )
    monkeypatch.setattr(neuralforecast.models, "DLinear", FakeDLinear)
    monkeypatch.setattr(neuralforecast.models, "HINT", FakeHINT)

    worker = PositionSeriesWorker(
        get_model_spec("nf-auto-hint"),
        {
            "max_steps": 2,
            "val_check_steps": 50,
            "batch_size": 8,
            "learning_rate": 0.001,
        },
        seed=1,
        device="cpu",
        precision="32",
    )

    output = worker._autohint(_history())

    base_model_config = captured["base_model_config"]
    assert isinstance(base_model_config, dict)
    assert base_model_config["max_steps"] == 2
    assert base_model_config["val_check_steps"] == 2
    assert output.metadata["base_model_config"]["max_steps"] == 2
    assert output.metadata["base_model_config"]["val_check_steps"] == 2
    assert captured["prediction_seed"] == 1

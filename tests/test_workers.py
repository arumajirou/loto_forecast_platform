

def test_neuralforecast_fit_receives_validation_window(monkeypatch):
    import sys
    import types

    import numpy as np
    import pandas as pd

    from loto.models.workers import PositionSeriesWorker

    captured = {}

    class FakeModel:
        def __init__(self, **kwargs):
            captured["model_kwargs"] = kwargs

    class FakeNeuralForecast:
        def __init__(self, models, freq):
            captured["freq"] = freq

        def fit(self, df, val_size=None):
            captured["val_size"] = val_size

        def predict(self):
            return pd.DataFrame({
                "unique_id": [f"n{i}" for i in range(1, 8)],
                "ds": pd.date_range("2026-01-01", periods=7),
                "FakeModel": np.arange(1, 8, dtype=float),
            })

    fake_models = types.SimpleNamespace(TiDE=FakeModel)
    fake_losses = types.SimpleNamespace(MAE=lambda: object())

    monkeypatch.setitem(
        sys.modules,
        "neuralforecast",
        types.SimpleNamespace(
            NeuralForecast=FakeNeuralForecast,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "neuralforecast.models",
        fake_models,
    )
    monkeypatch.setitem(
        sys.modules,
        "neuralforecast.losses.pytorch",
        fake_losses,
    )

    history = pd.DataFrame({
        "draw_date": pd.date_range(
            "2024-01-01",
            periods=50,
            freq="7D",
        ),
        **{
            f"n{i}": np.arange(50) + i
            for i in range(1, 8)
        },
    })

    spec = types.SimpleNamespace(
        class_name="TiDE",
        model_id="nf-tide",
        library="neuralforecast",
        default_params={},
    )

    worker = PositionSeriesWorker(
        spec,
        {"max_steps": 1},
        seed=42,
        device="cpu",
        precision="32",
    )

    worker.forecast(history)

    assert captured["val_size"] == 10

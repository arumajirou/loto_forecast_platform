from __future__ import annotations

import importlib.metadata as metadata
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from loto.mlforecast.contracts import AutoConfig, CoreConfig
from loto.mlforecast.factory import (
    auto_fit_kwargs,
    build_auto_forecast,
    build_core_forecast,
    core_fit_kwargs,
    hit_at_1_objective,
)
from loto.mlforecast.provenance import MLFORECAST_REQUIRED_VERSION


pytest.importorskip("mlforecast")
if metadata.version("mlforecast") != MLFORECAST_REQUIRED_VERSION:
    pytest.skip("runtime smoke requires the frozen MLForecast version", allow_module_level=True)


def _panel(rows: int = 36) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for series_index, unique_id in enumerate(("p1", "p2"), start=1):
        for ds in range(rows):
            value = float(series_index + (ds % 7))
            records.append({"unique_id": unique_id, "ds": ds, "y": value})
    return pd.DataFrame(records)


def _assert_prediction(prediction: pd.DataFrame, column: str) -> None:
    assert prediction.shape[0] == 2
    assert column in prediction
    assert np.isfinite(prediction[column].to_numpy(float)).all()


def test_core_ridge_fit_predict_save_load(tmp_path: Path) -> None:
    from mlforecast import MLForecast

    config = CoreConfig(models=["ridge"], lags=[1, 2, 7], cv_n_windows=2)
    model = build_core_forecast(config, seed=1)
    model.fit(
        _panel(),
        static_features=[],
        **core_fit_kwargs(config),
    )
    prediction = model.predict(h=1)
    _assert_prediction(prediction, "ridge")

    model_dir = tmp_path / "core"
    model_dir.mkdir()
    model.save(str(model_dir))
    loaded = MLForecast.load(str(model_dir))
    repeated = loaded.predict(h=1)
    _assert_prediction(repeated, "ridge")
    np.testing.assert_allclose(prediction["ridge"], repeated["ridge"], rtol=1e-8, atol=1e-8)


def test_auto_ridge_fit_predict_save_load(tmp_path: Path) -> None:
    from mlforecast import MLForecast

    config = AutoConfig(
        models=["AutoRidge"],
        season_length=1,
        n_windows=2,
        num_samples=2,
        sampler="tpe",
    )
    model = build_auto_forecast(config, static_features=[])
    kwargs = auto_fit_kwargs(config, seed=1)
    kwargs["h"] = 1
    model.fit(
        _panel(),
        loss=lambda validation, train_df, weight_col=None: hit_at_1_objective(
            validation,
            train_df,
            weight_col=weight_col,
        ),
        **{key: value for key, value in kwargs.items() if value is not None},
    )
    prediction = model.predict(h=1)
    _assert_prediction(prediction, "AutoRidge")

    model_dir = tmp_path / "auto-ridge"
    model_dir.mkdir()
    model.models_["AutoRidge"].save(str(model_dir))
    loaded = MLForecast.load(str(model_dir))
    repeated = loaded.predict(h=1)
    _assert_prediction(repeated, "AutoRidge")
    np.testing.assert_allclose(
        prediction["AutoRidge"],
        repeated["AutoRidge"],
        rtol=1e-8,
        atol=1e-8,
    )

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from loto.darts_campaign.local_models import (
    P5_LOCAL_MODEL_SPECS,
    build_local_model_requests,
    local_model_inventory,
    run_local_model_matrix,
)
from loto.darts_campaign.protocol import DartsRequest, GameGeometry, ModelIdentity


class FakePrediction:
    def __init__(self, values: np.ndarray) -> None:
        self._values = values

    def values(self) -> np.ndarray:
        return self._values


class FakeTimeSeries:
    def __init__(self, values: np.ndarray) -> None:
        self.values_array = values

    @classmethod
    def from_series(cls, series: pd.Series) -> FakeTimeSeries:
        return cls(series.to_numpy(float))


class FakeLocalModel:
    supports_multivariate = False
    supports_probabilistic_prediction = False

    def __init__(self, bias: float = 0.0) -> None:
        self.bias = bias
        self.last = 0.0

    def fit(self, series: FakeTimeSeries, verbose: bool = False) -> FakeLocalModel:
        del verbose
        self.last = float(series.values_array[-1])
        return self

    def predict(self, n: int, num_samples: int = 1) -> FakePrediction:
        del num_samples
        return FakePrediction(np.full((n, 1), self.last + self.bias))

    def save(self, path: str) -> None:
        del path

    @classmethod
    def load(cls, path: str) -> type[FakeLocalModel]:
        del path
        return cls()


def _models_module(*, omit: str | None = None, fail: str | None = None) -> SimpleNamespace:
    values: dict[str, object] = {}
    for spec in P5_LOCAL_MODEL_SPECS:
        if spec.public_name == omit:
            continue
        if spec.public_name == fail:

            class FailingModel(FakeLocalModel):
                def fit(self, series: FakeTimeSeries, verbose: bool = False) -> FailingModel:
                    del series, verbose
                    raise RuntimeError("synthetic failure")

            values[spec.public_name] = FailingModel
        else:
            values[spec.public_name] = FakeLocalModel
    return SimpleNamespace(**values)


def _request() -> DartsRequest:
    return DartsRequest(
        run_id="p5-local",
        mode="fit_predict",
        geometry=GameGeometry(game_id="numbers3", positions=3, min_value=0, max_value=9),
        model=ModelIdentity(public_name="NaiveMean"),
        horizon=1,
        artifact_dir="artifacts/darts/p5-local",
    )


def _frame(rows: int = 20) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "draw_no": np.arange(1, rows + 1),
            "n1": np.arange(rows) % 10,
            "n2": (np.arange(rows) + 1) % 10,
            "n3": (np.arange(rows) + 2) % 10,
        }
    )


def test_inventory_retains_all_nine_candidates_and_missing_class() -> None:
    rows = local_model_inventory(_models_module(omit="AutoARIMA"))
    assert len(rows) == 9
    by_name = {row["public_name"]: row for row in rows}
    assert by_name["AutoARIMA"]["status"] == "DEPENDENCY_MISSING"
    assert by_name["ARIMA"]["status"] == "AVAILABLE_NOT_EXECUTED"
    assert by_name["ARIMA"]["lifecycle_signatures"]["predict"] is not None


def test_build_requests_rejects_unknown_and_preserves_explicit_args() -> None:
    requests = build_local_model_requests(
        _request(),
        model_names=["NaiveMean", "ARIMA"],
        model_args_by_name={"ARIMA": {"bias": 1.5}},
    )
    assert [request.model.public_name for request in requests if request.model] == [
        "NaiveMean",
        "ARIMA",
    ]
    assert requests[1].model_args == {"bias": 1.5}
    with pytest.raises(ValueError, match="unknown P5 local models"):
        build_local_model_requests(_request(), model_names=["UnknownModel"])


def test_matrix_executes_all_candidates_with_identical_shape_and_no_mutation() -> None:
    frame = _frame()
    original = frame.copy(deep=True)
    rows = run_local_model_matrix(
        _request(),
        frame,
        models_module=_models_module(),
        timeseries_cls=FakeTimeSeries,
    )
    assert len(rows) == 9
    assert {row["status"] for row in rows} == {"SUCCEEDED_FAKE_OR_REAL_RUNTIME"}
    assert {tuple(row["prediction_shape"]) for row in rows} == {(3, 1)}
    pd.testing.assert_frame_equal(frame, original, check_exact=True)


def test_matrix_rejects_constructor_and_lifecycle_arguments_without_silent_drop() -> None:
    constructor = run_local_model_matrix(
        _request(),
        _frame(),
        model_names=["NaiveMean"],
        model_args_by_name={"NaiveMean": {"unknown": 1}},
        models_module=_models_module(),
        timeseries_cls=FakeTimeSeries,
    )
    assert constructor[0]["status"] == "INVALID_REQUEST"
    assert "rejected arguments" in constructor[0]["error"]

    template = _request().model_copy(update={"fit_args": {"not_supported": True}})
    lifecycle = run_local_model_matrix(
        template,
        _frame(),
        model_names=["NaiveMean"],
        models_module=_models_module(),
        timeseries_cls=FakeTimeSeries,
    )
    assert lifecycle[0]["status"] == "INVALID_REQUEST"
    assert "rejected arguments" in lifecycle[0]["error"]


def test_one_model_failure_does_not_stop_matrix() -> None:
    rows = run_local_model_matrix(
        _request(),
        _frame(),
        model_names=["NaiveMean", "Theta", "Croston"],
        models_module=_models_module(fail="Theta"),
        timeseries_cls=FakeTimeSeries,
    )
    by_name = {row["model"]: row for row in rows}
    assert by_name["NaiveMean"]["status"] == "SUCCEEDED_FAKE_OR_REAL_RUNTIME"
    assert by_name["Theta"]["status"] == "EXECUTION_FAILED"
    assert by_name["Croston"]["status"] == "SUCCEEDED_FAKE_OR_REAL_RUNTIME"


def test_campaign_minimum_history_fails_before_runtime_fit() -> None:
    rows = run_local_model_matrix(
        _request(),
        _frame(rows=4),
        model_names=["AutoARIMA"],
        models_module=_models_module(),
        timeseries_cls=FakeTimeSeries,
    )
    assert rows[0]["status"] == "INVALID_REQUEST"
    assert "requires at least" in rows[0]["error"]

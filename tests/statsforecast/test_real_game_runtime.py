from __future__ import annotations

from types import SimpleNamespace

import pytest

from loto.statsforecast.real_game_runtime import (
    RealGameLane,
    forecast_univariate_entry,
    lane_for_model,
    resolve_entry_parameters,
    resolved_model_spec,
)


class FakeARIMA:
    def __init__(self, order):
        self.order = order


class FakeWorker:
    last_init: dict[str, object] | None = None

    def __init__(
        self,
        spec,
        params,
        *,
        seed,
        device,
        precision,
        position_columns,
    ):
        type(self).last_init = {
            "spec": spec,
            "params": params,
            "seed": seed,
            "device": device,
            "precision": precision,
            "position_columns": position_columns,
        }

    def forecast(self, history):
        return SimpleNamespace(
            position_values=[1.0, 2.0],
            metadata={"history": history},
        )


def _entry(class_name: str = "ARIMA") -> SimpleNamespace:
    return SimpleNamespace(
        model_id=f"sf-{class_name.lower()}",
        family="arima",
        library="statsforecast",
        task="position_series",
        class_name=class_name,
        priority="p1",
        package="statsforecast",
        capabilities=("position",),
        default_params={},
        notes="",
    )


def test_lane_classification_is_explicit() -> None:
    assert lane_for_model("ARIMA") is RealGameLane.UNIVARIATE
    assert lane_for_model("SklearnModel") is RealGameLane.EXOGENOUS
    assert lane_for_model("NaNModel") is RealGameLane.EXPECTED_NEGATIVE_CONTROL


def test_resolve_entry_parameters_uses_certified_defaults() -> None:
    params = resolve_entry_parameters(
        _entry(),
        SimpleNamespace(ARIMA=FakeARIMA),
    )

    assert params == {"order": (1, 0, 0)}


def test_resolved_model_spec_carries_parameters() -> None:
    entry = _entry()
    spec = resolved_model_spec(entry, {"order": (2, 0, 0)})

    assert spec.model_id == entry.model_id
    assert spec.class_name == "ARIMA"
    assert spec.default_params == {"order": (2, 0, 0)}


def test_forecast_univariate_entry_passes_resolved_parameters_to_worker() -> None:
    result = forecast_univariate_entry(
        _entry(),
        history="history",
        position_columns=["n1", "n2"],
        seed=1,
        device="cpu",
        precision="32",
        models_module=SimpleNamespace(ARIMA=FakeARIMA),
        worker_class=FakeWorker,
    )

    assert result.metadata == {"history": "history"}
    assert FakeWorker.last_init is not None
    assert FakeWorker.last_init["params"] == {"order": (1, 0, 0)}
    assert FakeWorker.last_init["seed"] == 1
    assert FakeWorker.last_init["position_columns"] == ["n1", "n2"]


@pytest.mark.parametrize("model_name", ["SklearnModel", "NaNModel"])
def test_non_univariate_lanes_are_fail_visible(model_name: str) -> None:
    with pytest.raises(ValueError, match="not UNIVARIATE"):
        forecast_univariate_entry(
            _entry(model_name),
            history="history",
            position_columns=["n1"],
            models_module=SimpleNamespace(),
            worker_class=FakeWorker,
        )

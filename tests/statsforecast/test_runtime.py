from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from loto.statsforecast.contracts import RuntimeStatus
from loto.statsforecast.runtime import (
    StatsForecastRuntimeAdapter,
    constructor_argument_ledger,
    discover_runtime_inventory,
    validate_forecast_output,
)


class Naive:
    def __init__(self, alias: str = "Naive") -> None:
        self.alias = alias


class FakeCore:
    def __init__(self, *, models, freq, n_jobs) -> None:
        assert len(models) == 1
        assert freq == 1
        assert n_jobs == 1

    def forecast(self, *, df, h, level):
        assert list(level) == [80, 90]
        rows = []
        for unique_id in df["unique_id"].unique():
            rows.append({"unique_id": unique_id, "ds": 4, "Naive": 3.0})
        return pd.DataFrame(rows)


def panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "unique_id": ["d1", "d1", "d1", "d2", "d2", "d2"],
            "ds": [1, 2, 3, 1, 2, 3],
            "y": [1.0, 2.0, 3.0, 2.0, 3.0, 4.0],
        }
    )


def test_fake_runtime_executes_forecast_and_validates() -> None:
    adapter = StatsForecastRuntimeAdapter(
        core_class=FakeCore,
        models_module=SimpleNamespace(Naive=Naive),
    )
    prediction, evidence = adapter.forecast(
        panel(),
        model_name="Naive",
        freq=1,
        horizon=1,
    )
    assert len(prediction) == 2
    assert evidence["status"] is RuntimeStatus.VERIFIED


def test_nan_model_expected_negative_contract() -> None:
    prediction = pd.DataFrame(
        {"unique_id": ["d1"], "ds": [1], "NaNModel": [np.nan]}
    )
    evidence = validate_forecast_output(
        prediction,
        model_name="NaNModel",
        expected_rows=1,
    )
    assert evidence["status"] is RuntimeStatus.EXPECTED_NEGATIVE_PASS


def test_constructor_unknown_argument_rejected() -> None:
    with pytest.raises(ValueError, match="rejected"):
        constructor_argument_ledger(Naive, {"invented": 1})


def test_missing_dependency_is_retained_as_evidence(monkeypatch) -> None:
    monkeypatch.setattr(
        "loto.statsforecast.runtime.import_module",
        lambda _name: (_ for _ in ()).throw(ImportError("missing")),
    )
    result = discover_runtime_inventory()
    assert result["status"] is RuntimeStatus.DEPENDENCY_MISSING
    assert result["pinned_count"] == 41


def test_partial_runtime_inventory_is_not_verified() -> None:
    result = discover_runtime_inventory(SimpleNamespace(__all__=("Naive",), Naive=Naive))
    assert result["status"] is RuntimeStatus.INVENTORY_MISMATCH
    assert result["complete"] is False
    assert result["available_count"] == 1
    assert "AutoARIMA" in result["missing"]


def test_runtime_inventory_requires_every_project_model() -> None:
    namespace = SimpleNamespace(__all__=())
    inventory = __import__("loto.statsforecast.inventory", fromlist=["MODEL_NAMES"])
    for name in inventory.MODEL_NAMES:
        setattr(namespace, name, type(name, (), {}))
    result = discover_runtime_inventory(namespace)
    assert result["status"] is RuntimeStatus.VERIFIED
    assert result["complete"] is True
    assert result["missing"] == []


def test_seasonal_model_requires_season_length() -> None:
    class SeasonalNaive:
        def __init__(self, season_length: int) -> None:
            self.season_length = season_length

    adapter = StatsForecastRuntimeAdapter(
        core_class=FakeCore,
        models_module=SimpleNamespace(SeasonalNaive=SeasonalNaive),
    )
    with pytest.raises(ValueError, match="season_length"):
        adapter.forecast(
            panel(),
            model_name="SeasonalNaive",
            freq=1,
            horizon=1,
        )


def test_seasonal_model_requires_two_full_seasons() -> None:
    class SeasonalNaive:
        def __init__(self, season_length: int) -> None:
            self.season_length = season_length

    adapter = StatsForecastRuntimeAdapter(
        core_class=FakeCore,
        models_module=SimpleNamespace(SeasonalNaive=SeasonalNaive),
    )
    with pytest.raises(ValueError, match="at least 4 rows"):
        adapter.forecast(
            panel(),
            model_name="SeasonalNaive",
            freq=1,
            horizon=1,
            parameters={"season_length": 2},
        )


def test_forecast_output_rejects_wrong_series_composition() -> None:
    prediction = pd.DataFrame(
        {
            "unique_id": ["d1", "d3"],
            "ds": [4, 4],
            "Naive": [1.0, 2.0],
        }
    )
    evidence = validate_forecast_output(
        prediction,
        model_name="Naive",
        expected_rows=2,
        expected_unique_ids={"d1", "d2"},
        horizon=1,
    )
    assert evidence["status"] is RuntimeStatus.VALIDATION_FAILED
    assert evidence["series_horizon_ok"] is False


def test_ucm_uses_upstream_default_constructor() -> None:
    class UCM:
        def __init__(self, level: str = "local level") -> None:
            self.level = level

    adapter = StatsForecastRuntimeAdapter(
        core_class=FakeCore,
        models_module=SimpleNamespace(UCM=UCM),
    )
    model = adapter.build_model("UCM")
    assert model.level == "local level"


def test_multiseasonal_model_accepts_sequence_season_length() -> None:
    class MSTL:
        def __init__(self, season_length) -> None:
            self.season_length = season_length

    adapter = StatsForecastRuntimeAdapter(
        core_class=FakeCore,
        models_module=SimpleNamespace(MSTL=MSTL),
    )
    with pytest.raises(ValueError, match="at least 8 rows"):
        adapter.forecast(
            panel(),
            model_name="MSTL",
            freq=1,
            horizon=1,
            parameters={"season_length": [2, 4]},
        )


def test_conformal_seasonal_pool_does_not_require_two_seasons() -> None:
    class ConformalSeasonalPool:
        def __init__(self, season_length: int) -> None:
            self.season_length = season_length

    adapter = StatsForecastRuntimeAdapter(
        core_class=FakeCore,
        models_module=SimpleNamespace(ConformalSeasonalPool=ConformalSeasonalPool),
    )
    _, evidence = adapter.forecast(
        panel(),
        model_name="ConformalSeasonalPool",
        freq=1,
        horizon=1,
        parameters={"season_length": 12},
    )
    assert evidence["status"] is RuntimeStatus.VERIFIED

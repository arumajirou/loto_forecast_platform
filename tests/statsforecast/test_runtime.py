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

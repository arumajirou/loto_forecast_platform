from __future__ import annotations

from types import SimpleNamespace

from loto.darts_campaign.discovery import PUBLIC_FORECASTING_EXPORTS_0_46_1, discover_models


def test_static_export_count_is_versioned() -> None:
    assert len(PUBLIC_FORECASTING_EXPORTS_0_46_1) == 58
    assert len(set(PUBLIC_FORECASTING_EXPORTS_0_46_1)) == 58


def test_discovery_retains_import_failures() -> None:
    class Good:
        def fit(self, series):
            return self

        def predict(self, n):
            return [1.0] * n

    class Module(SimpleNamespace):
        def __getattr__(self, name):
            if name == "Missing":
                raise ModuleNotFoundError("optional dependency")
            raise AttributeError(name)

    rows = discover_models(Module(Good=Good), names=("Good", "Missing"))
    assert rows[0]["status"] == "IMPORTED"
    assert rows[0]["fit_signature"] is not None
    assert rows[1]["status"] == "DEPENDENCY_MISSING"

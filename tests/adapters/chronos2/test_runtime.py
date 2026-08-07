from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from loto.adapters.chronos2 import runtime
from loto.adapters.chronos2.contracts import Chronos2RequestV2
from loto.adapters.chronos2.geometry import game_geometry_preset
from loto.adapters.chronos2.manifest import CHRONOS_MODEL_REVISION


class FakeParameter:
    device = "cpu"


class FakeModel:
    device = "cpu"

    def parameters(self):
        yield FakeParameter()


class FakePipeline:
    model = FakeModel()

    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode

    def predict_df(self, df: pd.DataFrame, **kwargs: Any) -> pd.DataFrame:
        horizon = int(kwargs["prediction_length"])
        quantiles = list(kwargs["quantile_levels"])
        target = kwargs["target"]
        item_ids = list(dict.fromkeys(df["item_id"].tolist()))
        rows: list[dict[str, object]] = []
        if isinstance(target, list):
            pairs = [(item_ids[0], name) for name in target]
        else:
            pairs = [(item_id, str(target)) for item_id in item_ids]
        start = pd.Timestamp(df["timestamp"].max())
        for position_index, (item_id, target_name) in enumerate(pairs, start=1):
            for step in range(1, horizon + 1):
                base = float(position_index * 10 + step)
                row: dict[str, object] = {
                    "item_id": item_id,
                    "timestamp": start + pd.Timedelta(days=step),
                    "target_name": target_name,
                    "predictions": base,
                }
                for quantile in quantiles:
                    value = base + quantile - 0.5
                    if self.mode == "cross" and quantile == quantiles[-1]:
                        value = base - 10
                    if self.mode == "nonfinite" and quantile == quantiles[0]:
                        value = np.nan
                    row[str(quantile)] = value
                rows.append(row)
        return pd.DataFrame(rows)


def make_request(layout: str = "position_local", horizon: int = 2) -> Chronos2RequestV2:
    geometry, columns = game_geometry_preset("numbers3")
    history = []
    for index in range(4):
        history.append(
            {
                "draw_no": index + 1,
                "draw_date": f"2026-04-{index + 1:02d}",
                "n1": index,
                "n2": index + 1,
                "n3": index + 2,
            }
        )
    return Chronos2RequestV2.model_validate(
        {
            "schema_version": 2,
            "run_id": f"runtime-{layout}-{horizon}",
            "revision": CHRONOS_MODEL_REVISION,
            "game_geometry": geometry.model_dump(mode="json"),
            "series_layout": layout,
            "position_columns": columns,
            "history": history,
            "context_length": 64,
            "prediction_length": horizon,
            "quantile_levels": [0.1, 0.5, 0.9],
            "cross_learning": layout == "position_panel",
            "device": "cpu",
            "local_files_only": True,
        }
    )


def install_test_patches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime.importlib.metadata, "version", lambda _: "2.3.1")
    monkeypatch.setattr(runtime, "_nvidia_process_evidence", lambda _: (None, None))


@pytest.mark.parametrize("layout", ["position_local", "position_panel", "position_multivariate"])
def test_runtime_preserves_quantiles_and_shape(
    monkeypatch: pytest.MonkeyPatch, layout: str
) -> None:
    install_test_patches(monkeypatch)
    request = make_request(layout=layout, horizon=5)
    response = runtime.run_prediction(request, pipeline_loader=lambda _: FakePipeline())
    assert response.status == "OK"
    assert len(response.point_forecast) == 3
    assert all(len(row) == 5 for row in response.point_forecast)
    assert set(response.quantiles) == {"0.1", "0.5", "0.9"}
    assert response.mean_forecast == ()
    assert response.median_forecast == response.point_forecast
    assert "CHRONOS2_2_3_1_POINT_IS_MEDIAN_NOT_ARITHMETIC_MEAN" in response.warnings


def test_context_longer_than_history_is_not_applicable(monkeypatch: pytest.MonkeyPatch) -> None:
    install_test_patches(monkeypatch)
    response = runtime.run_prediction(make_request(), pipeline_loader=lambda _: FakePipeline())
    entry = next(item for item in response.argument_ledger if item.argument == "context_length")
    assert entry.status.value == "NOT_APPLICABLE"
    assert response.effective_arguments["context_length"] == 4


def test_quantile_crossing_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    install_test_patches(monkeypatch)
    with pytest.raises(ValueError, match="quantile crossing"):
        runtime.run_prediction(make_request(), pipeline_loader=lambda _: FakePipeline("cross"))


def test_non_finite_quantile_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    install_test_patches(monkeypatch)
    with pytest.raises(ValueError, match="non-finite"):
        runtime.run_prediction(make_request(), pipeline_loader=lambda _: FakePipeline("nonfinite"))

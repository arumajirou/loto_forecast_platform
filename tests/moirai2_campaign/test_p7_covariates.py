from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from loto.adapters.moirai2.adapter import Moirai2Adapter, Moirai2AdapterError
from loto.adapters.moirai2.contracts import (
    Moirai2ProviderRequest,
    Moirai2ProviderResponse,
)
from loto.moirai2_campaign.covariates import (
    attach_covariates,
    compile_covariates,
)
from loto.moirai2_campaign.token_geometry import (
    TokenGeometryError,
    calculate_token_geometry,
)


def _request_payload() -> dict:
    return {
        "run_id": "p7-contract",
        "license_lane": "personal_noncommercial_research",
        "game_geometry": {
            "game_id": "numbers3-n1",
            "position_count": 1,
            "candidate_min": 0,
            "candidate_max": 9,
            "strictly_increasing": False,
        },
        "series_layout": "position_univariate",
        "position_columns": ["n1"],
        "history": [{"n1": float(index)} for index in range(16)],
        "timestamps": list(range(1, 17)),
        "context_length": 16,
        "prediction_length": 2,
        "past_covariates": {"rolling": [float(index) for index in range(16)]},
        "future_covariates": {
            "weekday": [float(index % 7) for index in range(18)]
        },
        "future_covariate_availability": {
            "weekday": "known_at_prediction_time"
        },
    }


def test_covariate_compiler_sorts_slices_hashes_and_attaches_native_fields() -> None:
    bundle = compile_covariates(
        history_length=6,
        context_length=4,
        prediction_length=2,
        past_covariates={
            "rolling": [10, 11, 12, 13, 14, 15],
            "gap": [20, 21, 22, 23, 24, 25],
        },
        future_covariates={
            "weekday": [0, 1, 2, 3, 4, 5, 6, 0],
            "draw_no": [1, 2, 3, 4, 5, 6, 7, 8],
        },
        future_covariate_availability={
            "weekday": "known_at_prediction_time",
            "draw_no": "known_at_prediction_time",
        },
        time_semantics="draw_sequence",
        context_timestamps=[3, 4, 5, 6],
        target_time_length=4,
    )
    assert bundle.past.names == ("gap", "rolling")
    assert bundle.known_future.names == ("draw_no", "weekday")
    assert bundle.past_feat_dynamic_real is not None
    assert bundle.feat_dynamic_real is not None
    assert bundle.past_feat_dynamic_real.shape == (2, 4)
    assert bundle.feat_dynamic_real.shape == (2, 6)
    assert bundle.past.sha256
    assert bundle.known_future.sha256
    assert bundle.known_future_tail_sha256
    entry = attach_covariates({"start": "x", "target": np.zeros((1, 4))}, bundle)
    assert "past_feat_dynamic_real" in entry
    assert "feat_dynamic_real" in entry


def test_calendar_covariates_preserve_missing_periods() -> None:
    timestamps = [
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 3, tzinfo=timezone.utc),
        datetime(2026, 1, 4, tzinfo=timezone.utc),
    ]
    bundle = compile_covariates(
        history_length=3,
        context_length=3,
        prediction_length=1,
        past_covariates={"rolling": [1, 2, 3]},
        future_covariates={"weekday": [4, 6, 0, 1]},
        future_covariate_availability={"weekday": "known_at_prediction_time"},
        time_semantics="calendar_time",
        context_timestamps=timestamps,
        target_time_length=4,
    )
    assert bundle.past_feat_dynamic_real is not None
    assert bundle.feat_dynamic_real is not None
    assert np.isnan(bundle.past_feat_dynamic_real[0, 1])
    assert np.isnan(bundle.feat_dynamic_real[0, 1])
    assert bundle.feat_dynamic_real[0, -1] == 1


def test_contract_rejects_collisions_and_counts_covariate_tokens() -> None:
    payload = _request_payload()
    payload["past_covariates"] = {"n1": [1.0] * 16}
    with pytest.raises(ValidationError, match="must not overlap"):
        Moirai2ProviderRequest.model_validate(payload)

    with pytest.raises(TokenGeometryError, match="total token count"):
        calculate_token_geometry(
            target_dim=7,
            feat_dynamic_real_dim=30,
            past_feat_dynamic_real_dim=30,
            context_length=128,
            prediction_length=5,
        )


def test_adapter_rejects_changed_covariate_identity() -> None:
    request = Moirai2ProviderRequest.model_validate(_request_payload())
    response = Moirai2ProviderResponse.model_validate(
        {
            "status": "OK",
            "phase": "predict",
            "message": "ok",
            "runtime_evidence": {
                "process_id": 1,
                "package_version": "2.0.0",
                "runtime_lane": "supported-py311",
                "requested_device": "cpu",
                "execution_device": "cpu",
                "model_parameter_device": "cpu",
                "output_shape": [2, 1],
                "all_quantiles_finite": True,
                "quantile_monotonicity": True,
                "cpu_fallback": False,
            },
            "gpu_evidence": {
                "requested_device": "cpu",
                "execution_device": "cpu",
                "cuda_available": False,
                "provider_pid": 1,
                "gpu_pid": None,
                "peak_vram_bytes": 0,
                "cpu_fallback": False,
            },
            "covariate_evidence": {
                "past": {"names": ["wrong"], "shape": [1, 16], "sha256": "a" * 64},
                "known_future": {
                    "names": ["weekday"],
                    "shape": [1, 18],
                    "sha256": "b" * 64,
                },
                "known_future_tail_sha256": "c" * 64,
                "chronology_valid": True,
                "availability_verified": True,
                "actuals_used": False,
            },
        }
    )
    with pytest.raises(Moirai2AdapterError, match="past covariate names"):
        Moirai2Adapter._verify_covariate_response(request, response)


def _load_runner():
    path = Path(__file__).resolve().parents[2] / "scripts" / "run_moirai2_provider.py"
    spec = importlib.util.spec_from_file_location("p7_runner_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runner_wires_native_fields_and_univariate_shape(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeDevice:
        type = "cpu"

        def __str__(self) -> str:
            return "cpu"

    class FakeModule:
        @classmethod
        def from_pretrained(cls, path: str, local_files_only: bool):
            return cls()

        def to(self, device: str):
            return self

        def eval(self):
            return self

        def parameters(self):
            return iter([types.SimpleNamespace(device=FakeDevice())])

    class FakeForecast:
        def quantile(self, level: float) -> np.ndarray:
            return np.full((2, 1), level, dtype=np.float64)

    class FakePredictor:
        def predict(self, dataset):
            captured["dataset_at_predict"] = dataset
            return iter([FakeForecast()])

    class FakeForecastModel:
        def __init__(self, **kwargs):
            captured["model_kwargs"] = kwargs

        def create_predictor(self, batch_size: int, device: str):
            return FakePredictor()

    class FakeListDataset(list):
        def __init__(self, entries, *, freq: str, one_dim_target: bool):
            super().__init__(entries)
            captured["dataset_args"] = (freq, one_dim_target)

    torch = types.ModuleType("torch")
    torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    common = types.ModuleType("gluonts.dataset.common")
    common.ListDataset = FakeListDataset
    dataset = types.ModuleType("gluonts.dataset")
    dataset.common = common
    gluonts = types.ModuleType("gluonts")
    gluonts.dataset = dataset
    moirai2 = types.ModuleType("uni2ts.model.moirai2")
    moirai2.Moirai2Module = FakeModule
    moirai2.Moirai2Forecast = FakeForecastModel
    model = types.ModuleType("uni2ts.model")
    model.moirai2 = moirai2
    uni2ts = types.ModuleType("uni2ts")
    uni2ts.model = model
    for name, module in {
        "torch": torch,
        "gluonts": gluonts,
        "gluonts.dataset": dataset,
        "gluonts.dataset.common": common,
        "uni2ts": uni2ts,
        "uni2ts.model": model,
        "uni2ts.model.moirai2": moirai2,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    runner = _load_runner()
    monkeypatch.setattr(runner.importlib.metadata, "version", lambda _: "2.0.0")
    monkeypatch.setattr(runner, "_snapshot", lambda _: Path("/tmp/fixed-snapshot"))
    monkeypatch.setattr(
        runner,
        "verify_snapshot",
        lambda path: {"snapshot_path": str(path), "status": "VERIFIED"},
    )
    response = runner.run_provider(
        Moirai2ProviderRequest.model_validate(_request_payload()),
        runtime_lane="supported-py311",
    )
    entry = captured["dataset_at_predict"][0]
    assert entry["target"].shape == (16,)
    assert entry["past_feat_dynamic_real"].shape == (1, 16)
    assert entry["feat_dynamic_real"].shape == (1, 18)
    assert captured["dataset_args"] == ("D", True)
    model_kwargs = captured["model_kwargs"]
    assert model_kwargs["past_feat_dynamic_real_dim"] == 1
    assert model_kwargs["feat_dynamic_real_dim"] == 1
    assert response["covariate_evidence"]["actuals_used"] is False

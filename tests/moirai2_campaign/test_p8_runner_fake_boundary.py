from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch


class _Response:
    def __init__(self, **payload):
        self.payload = payload

    def model_dump(self, mode: str):
        assert mode == "json"
        return self.payload


class _License:
    def as_dict(self):
        return {
            "code_license": "Apache-2.0",
            "model_license": "CC-BY-NC-4.0",
            "license_lane": "personal_noncommercial_research",
            "research_only": True,
            "production_champion_eligible": False,
            "automatic_promotion": False,
            "commercial_deployment_certified": False,
        }


class _Matrix:
    def __init__(self):
        self.names = ()


class _Covariates:
    past_dim = 0
    known_future_dim = 0
    past = _Matrix()
    known_future = _Matrix()

    def as_dict(self):
        return {
            "past": {"names": [], "shape": [0, 16], "sha256": None},
            "known_future": {"names": [], "shape": [0, 17], "sha256": None},
            "known_future_tail_sha256": None,
            "chronology_valid": True,
            "availability_verified": True,
            "actuals_used": False,
        }


class _Geometry:
    def as_dict(self):
        return {"total_tokens": 2}


class _TimeAxis:
    start = "2000-01-01"
    target = np.arange(16, dtype=np.float32).reshape(1, 16)
    frequency = "D"
    frequency_policy = "one_period_per_draw"
    missing_period_policy = "forbid_missing_draw_sequence"
    mapping_sha256 = "f" * 64


class _Module(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.ones(1))

    @classmethod
    def from_pretrained(cls, *_args, **_kwargs):
        return cls()


class _Forecast:
    pass


class _Predictor:
    device = "cpu"

    def __init__(self, model):
        self.model = model

    def predict(self, _dataset):
        self.model(torch.ones(1, 3))
        return iter([_Forecast()])


class _Model(torch.nn.Module):
    def __init__(self, module, **_kwargs):
        super().__init__()
        self.module_ref = module

    def forward(self, value):
        return value + 1

    def create_predictor(self, batch_size, device):
        assert batch_size == 1
        assert device == "cpu"
        return _Predictor(self)


def _install_module(monkeypatch, name: str, **attributes) -> None:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)


def _load_runner(monkeypatch):
    _install_module(
        monkeypatch,
        "loto.adapters.moirai2.contracts",
        Moirai2ProviderRequest=object,
        Moirai2ProviderResponse=_Response,
    )
    _install_module(
        monkeypatch,
        "loto.moirai2_campaign.covariates",
        attach_covariates=lambda entry, _covariates: entry,
        compile_covariates=lambda **_kwargs: _Covariates(),
    )
    _install_module(
        monkeypatch,
        "loto.moirai2_campaign.license_policy",
        evaluate_license_lane=lambda _lane: _License(),
    )
    _install_module(
        monkeypatch,
        "loto.moirai2_campaign.model_manifest",
        MODEL_ID="moirai-2.0-r-small",
        MODEL_REVISION="revision",
        NATIVE_QUANTILE_LEVELS=(0.1, 0.5, 0.9),
        REPO_ID="Salesforce/moirai-2.0-R-small",
        UNI2TS_VERSION="2.0.0",
    )
    _install_module(
        monkeypatch,
        "loto.moirai2_campaign.provenance",
        verify_snapshot=lambda _path: {
            "model_revision": "revision",
            "config_sha256": "a" * 64,
            "weight_sha256": "b" * 64,
        },
    )
    _install_module(
        monkeypatch,
        "loto.moirai2_campaign.quantiles",
        extract_native_quantiles=lambda *_args, **_kwargs: {
            "0.1": [[0.1]],
            "0.5": [[0.5]],
            "0.9": [[0.9]],
        },
        median_point_forecast=lambda quantiles: quantiles["0.5"],
    )
    _install_module(
        monkeypatch,
        "loto.moirai2_campaign.time_adapter",
        build_calendar_time_axis=lambda *_args, **_kwargs: _TimeAxis(),
        build_draw_sequence_axis=lambda *_args, **_kwargs: _TimeAxis(),
    )
    _install_module(
        monkeypatch,
        "loto.moirai2_campaign.token_geometry",
        calculate_token_geometry=lambda **_kwargs: _Geometry(),
    )
    _install_module(monkeypatch, "gluonts")
    _install_module(monkeypatch, "gluonts.dataset")
    _install_module(
        monkeypatch,
        "gluonts.dataset.common",
        ListDataset=lambda entries, **_kwargs: entries,
    )
    _install_module(monkeypatch, "uni2ts")
    _install_module(monkeypatch, "uni2ts.model")
    _install_module(
        monkeypatch,
        "uni2ts.model.moirai2",
        Moirai2Forecast=_Model,
        Moirai2Module=_Module,
    )
    monkeypatch.setattr("importlib.metadata.version", lambda _name: "2.0.0")
    path = Path(__file__).parents[2] / "scripts" / "run_moirai2_provider.py"
    spec = importlib.util.spec_from_file_location("p8_runner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runner_records_real_forward_device_boundary(monkeypatch, tmp_path) -> None:
    runner = _load_runner(monkeypatch)
    request = SimpleNamespace(
        operation=SimpleNamespace(value="predict"),
        license_lane="personal_noncommercial_research",
        past_covariates={},
        future_covariates={},
        future_covariate_availability={},
        game_geometry=SimpleNamespace(position_count=1),
        context_length=16,
        prediction_length=1,
        device="cpu",
        seed=1,
        snapshot_path=str(tmp_path),
        history=[{"n1": float(index)} for index in range(16)],
        position_columns=["n1"],
        timestamps=[],
        time_semantics=SimpleNamespace(value="draw_sequence"),
        batch_size=1,
    )
    payload = runner.run_provider(request, runtime_lane="supported-py311")
    evidence = payload["effective_arguments"]["forward_device_evidence"]
    assert evidence["forward_call_count"] == 1
    assert evidence["input_tensor_devices"] == ["cpu"]
    assert evidence["output_tensor_devices"] == ["cpu"]
    assert payload["effective_arguments"]["predictor_device"] == "cpu"
    assert payload["runtime_evidence"]["execution_device"] == "cpu"
    assert payload["gpu_evidence"]["gpu_pid"] is None

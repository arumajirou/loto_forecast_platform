# ruff: noqa: E402
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROVIDER_SRC = ROOT / "environments" / "gluonts-compat" / "src"
sys.path.insert(0, str(PROVIDER_SRC))

from loto_gluonts_provider import serialization_runtime as runtime
from loto_gluonts_provider.protocol import DatasetItem, GluonTSProviderRequest
from loto_gluonts_provider.serialization import LifecycleOutcome

VERSIONS = {
    "gluonts": "0.16.3",
    "torch": "2.9.1",
    "lightning": "2.4.0",
    "pytorch_lightning": "2.4.0",
    "numpy": "2.0.0",
    "pandas": "2.2.0",
}


class FakeParameter:
    device = "cpu"


class FakeNetwork:
    def parameters(self):
        return [FakeParameter()]


class FakeForecast:
    mean = np.asarray([3.25], dtype=float)


class FakePredictor:
    prediction_net = FakeNetwork()

    def predict(self, dataset):
        yield FakeForecast()

    def serialize(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        (path / "model.json").write_text(
            json.dumps({"model": "DeepAREstimator"}),
            encoding="utf-8",
        )

    @classmethod
    def deserialize(cls, path: Path):
        assert (path / "model.json").exists()
        return cls()


class FakeEstimator:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def train(self, training_data):
        assert list(training_data)
        return FakePredictor()


class FakeTorch:
    @staticmethod
    def manual_seed(seed):
        return None

    @staticmethod
    def set_num_threads(count):
        return None


def list_dataset(rows, freq):
    return list(rows)


def bindings():
    return runtime.RuntimeBindings(
        np=np,
        pd=pd,
        torch=FakeTorch(),
        list_dataset=list_dataset,
        deep_ar_estimator=FakeEstimator,
        student_t_output=lambda: object(),
        predictor_class=FakePredictor,
    )


def request(tmp_path: Path) -> GluonTSProviderRequest:
    return GluonTSProviderRequest(
        request_id="fit-1",
        run_id="run-1",
        lane="compat",
        operation="fit_predict",
        model_class="DeepAREstimator",
        prediction_length=1,
        context_length=8,
        seed=1,
        freq="D",
        dataset=[
            DatasetItem(
                item_id="series-1",
                start="2000-01-01",
                target=[float(index) for index in range(32)],
            )
        ],
        artifact_dir=str(tmp_path / "predictor"),
    )


def test_fit_then_reload_in_new_pid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runtime.os, "getpid", lambda: 101)
    fit, rows = runtime.fit_predict_serialize(
        request(tmp_path),
        "compat",
        bindings_loader=bindings,
        observed_versions=VERSIONS,
    )
    assert fit.outcome is LifecycleOutcome.VERIFIED
    assert rows[0].mean == 3.25
    assert fit.artifact_manifest is not None

    load_request = request(tmp_path).model_copy(
        update={
            "request_id": "load-1",
            "operation": "load_predict",
            "dataset": [],
        }
    )
    monkeypatch.setattr(runtime.os, "getpid", lambda: 202)
    reload_result, reload_rows = runtime.load_predict_serialized(
        load_request,
        "compat",
        bindings_loader=bindings,
        observed_versions=VERSIONS,
    )
    assert reload_result.outcome is LifecycleOutcome.VERIFIED
    assert reload_result.fit_process_id == 101
    assert reload_result.load_process_id == 202
    assert reload_rows[0].mean == 3.25


def test_reload_rejects_same_process(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runtime.os, "getpid", lambda: 101)
    fit, _ = runtime.fit_predict_serialize(
        request(tmp_path),
        "compat",
        bindings_loader=bindings,
        observed_versions=VERSIONS,
    )
    assert fit.outcome is LifecycleOutcome.VERIFIED

    load_request = request(tmp_path).model_copy(update={"operation": "load_predict", "dataset": []})
    result, _ = runtime.load_predict_serialized(
        load_request,
        "compat",
        bindings_loader=bindings,
        observed_versions=VERSIONS,
    )
    assert result.outcome is LifecycleOutcome.FAILED
    assert "new process" in result.errors[0]


def test_reload_rejects_tampered_artifact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(runtime.os, "getpid", lambda: 101)
    fit, _ = runtime.fit_predict_serialize(
        request(tmp_path),
        "compat",
        bindings_loader=bindings,
        observed_versions=VERSIONS,
    )
    assert fit.outcome is LifecycleOutcome.VERIFIED
    (tmp_path / "predictor" / "model.json").write_text("tampered", encoding="utf-8")

    monkeypatch.setattr(runtime.os, "getpid", lambda: 202)
    load_request = request(tmp_path).model_copy(update={"operation": "load_predict", "dataset": []})
    result, _ = runtime.load_predict_serialized(
        load_request,
        "compat",
        bindings_loader=bindings,
        observed_versions=VERSIONS,
    )
    assert result.outcome is LifecycleOutcome.FAILED
    assert "inventory mismatch" in result.errors[0]

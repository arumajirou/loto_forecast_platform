from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
PROVIDER_SRC = ROOT / "environments" / "gluonts-compat" / "src"
sys.path.insert(0, str(PROVIDER_SRC))

from loto_gluonts_provider import p6_fit_runtime, p6_reload_runtime, p6_runtime
from loto_gluonts_provider.p6_contract import (
    FailureCategory,
    P6DatasetItem,
    P6Operation,
    P6ProviderRequest,
    P6Status,
)

from loto.adapters.gluonts.p6_registry import model_specs


class FakeTorch:
    @staticmethod
    def manual_seed(seed: int) -> None:
        assert seed == 1

    @staticmethod
    def set_num_threads(threads: int) -> None:
        assert threads == 1


class FakePandas:
    @staticmethod
    def Period(value: str, freq: str) -> str:
        return f"{value}:{freq}"


class FakeParameter:
    device = "cpu"


class FakeNetwork:
    @staticmethod
    def parameters() -> list[FakeParameter]:
        return [FakeParameter()]


class FakeForecast:
    mean = np.asarray([3.25], dtype=float)


class FakePredictor:
    prediction_net = FakeNetwork()

    def predict(self, dataset: object):
        assert dataset
        yield FakeForecast()

    def serialize(self, path: Path) -> None:
        (path / "predictor.json").write_text(
            json.dumps({"model": "fake"}) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def deserialize(cls, path: Path) -> FakePredictor:
        assert (path / "predictor.json").exists()
        return cls()


class FakeEstimator:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def train(self, training_data: object) -> FakePredictor:
        assert training_data
        return FakePredictor()


class BadSignatureEstimator:
    def __init__(self, impossible: int) -> None:
        self.impossible = impossible


class FakeStudentTOutput:
    pass


def bindings(estimator: type = FakeEstimator) -> p6_runtime.RuntimeBindings:
    return p6_runtime.RuntimeBindings(
        np=np,
        pd=FakePandas,
        torch=FakeTorch,
        list_dataset=lambda rows, freq: list(rows),
        predictor_class=FakePredictor,
        estimators={spec.model_class: estimator for spec in model_specs()},
        student_t_output=FakeStudentTOutput,
    )


def versions() -> dict[str, str | None]:
    return {
        "gluonts": "0.16.3",
        "torch": "2.9.1",
        "lightning": "2.4.0",
        "pytorch-lightning": None,
        "numpy": "2.0.0",
        "pandas": "2.2.0",
    }


def item() -> P6DatasetItem:
    return P6DatasetItem(
        item_id="series",
        start="2000-01-01",
        target=[float(index % 7) for index in range(64)],
    )


@pytest.mark.parametrize("spec", model_specs(), ids=lambda spec: spec.model_class)
def test_all_nine_models_fit_serialize_and_reload(
    spec,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_dir = tmp_path / spec.model_class
    fit_request = P6ProviderRequest(
        request_id=f"{spec.model_class}-fit",
        run_id="p6",
        lane="compat",
        operation=P6Operation.FIT_SERIALIZE,
        model_class=spec.model_class,
        distribution_output=spec.certified_distributions[0],
        prediction_length=1,
        context_length=(spec.default_context_length if spec.supports_context_length else None),
        artifact_dir=str(artifact_dir),
        dataset=[item()],
    )
    monkeypatch.setattr(p6_fit_runtime.os, "getpid", lambda: 1001)
    fit = p6_runtime.fit_serialize(
        fit_request,
        bindings_loader=bindings,
        observed_versions=versions(),
    )
    assert fit.status is P6Status.VERIFIED
    assert fit.artifact_manifest is not None
    assert fit.artifact_manifest.model_class == spec.model_class

    load_request = P6ProviderRequest(
        request_id=f"{spec.model_class}-load",
        run_id="p6",
        lane="compat",
        operation=P6Operation.LOAD_PREDICT,
        model_class=spec.model_class,
        distribution_output=spec.certified_distributions[0],
        prediction_length=1,
        context_length=(spec.default_context_length if spec.supports_context_length else None),
        artifact_dir=str(artifact_dir),
    )
    monkeypatch.setattr(p6_reload_runtime.os, "getpid", lambda: 1002)
    reload = p6_runtime.load_predict(
        load_request,
        bindings_loader=bindings,
        observed_versions=versions(),
    )
    assert reload.status is P6Status.VERIFIED
    assert reload.fit_process_id == 1001
    assert reload.process_id == 1002
    assert reload.artifact_manifest_sha256 == fit.artifact_manifest_sha256


def test_unknown_constructor_override_is_rejected(tmp_path: Path) -> None:
    request = P6ProviderRequest(
        request_id="fit",
        run_id="p6",
        lane="compat",
        operation=P6Operation.FIT_SERIALIZE,
        model_class="DeepAREstimator",
        distribution_output="StudentTOutput",
        prediction_length=1,
        context_length=8,
        artifact_dir=str(tmp_path / "predictor"),
        dataset=[item()],
        constructor_overrides={"not_a_real_argument": 1},
    )
    evidence = p6_runtime.fit_serialize(
        request,
        bindings_loader=bindings,
        observed_versions=versions(),
    )
    assert evidence.status is P6Status.FAILED
    assert evidence.failure_category is FailureCategory.UNSUPPORTED_ARGUMENT


def test_signature_mismatch_is_fail_closed(tmp_path: Path) -> None:
    request = P6ProviderRequest(
        request_id="fit",
        run_id="p6",
        lane="compat",
        operation=P6Operation.FIT_SERIALIZE,
        model_class="DeepAREstimator",
        distribution_output="StudentTOutput",
        prediction_length=1,
        context_length=8,
        artifact_dir=str(tmp_path / "predictor"),
        dataset=[item()],
    )
    evidence = p6_runtime.fit_serialize(
        request,
        bindings_loader=lambda: bindings(BadSignatureEstimator),
        observed_versions=versions(),
    )
    assert evidence.status is P6Status.FAILED
    assert evidence.failure_category is FailureCategory.SIGNATURE_MISMATCH


def test_missing_runtime_is_blocked(tmp_path: Path) -> None:
    request = P6ProviderRequest(
        request_id="fit",
        run_id="p6",
        lane="compat",
        operation=P6Operation.FIT_SERIALIZE,
        model_class="DeepAREstimator",
        prediction_length=1,
        context_length=8,
        artifact_dir=str(tmp_path / "predictor"),
        dataset=[item()],
    )
    evidence = p6_runtime.fit_serialize(
        request,
        bindings_loader=bindings,
        observed_versions={"gluonts": None, "torch": None},
    )
    assert evidence.status is P6Status.BLOCKED
    assert evidence.failure_category is FailureCategory.VERSION_MISMATCH

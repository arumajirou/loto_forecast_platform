from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from loto.adapters.autogluon import covariate_capability_provider as module
from loto.adapters.autogluon.contracts import ProviderOperation


@dataclass
class FakePlan:
    selected_model_ids: tuple[str, ...]
    fit_kwargs: dict


class FakeRequestModel:
    request = None

    @classmethod
    def model_validate(cls, payload):
        return cls.request


def request(
    tmp_path,
    *,
    operation=ProviderOperation.FIT_PREDICT_SAVE,
    mode="explicit_single_model",
):
    return SimpleNamespace(
        artifact_dir=str(tmp_path),
        operation=operation,
        execution_mode=SimpleNamespace(value=mode),
        predictor=SimpleNamespace(known_covariates_names=("holiday",)),
        covariates=SimpleNamespace(past_covariates_names=(), static_feature_names=()),
    )


def setup(monkeypatch, tmp_path, *, operation=ProviderOperation.FIT_PREDICT_SAVE):
    current = request(tmp_path, operation=operation)
    FakeRequestModel.request = current
    monkeypatch.setattr(module, "ProviderRequestV2Covariates", FakeRequestModel)
    monkeypatch.setattr(
        module,
        "build_execution_plan",
        lambda value: FakePlan(
            ("Naive",),
            {"hyperparameters": {"Naive": {"covariate_regressor": "GBM"}}},
        ),
    )
    return current


def test_fit_persists_and_exposes_capability_context(monkeypatch, tmp_path) -> None:
    setup(monkeypatch, tmp_path)
    monkeypatch.setattr(
        module,
        "run_provider_v2_covariates",
        lambda payload, runtime=None: {"status": "OK", "metadata": {}, "artifacts": {}},
    )
    response = module.run_provider_v2_covariates_guarded({"run_id": "fit"})
    assert response["status"] == "OK"
    decision = response["metadata"]["covariate_capability_decision"]
    assert decision["selected_model_ids"] == ["Naive"]
    path = tmp_path / module.CAPABILITY_CONTEXT_FILENAME
    assert path.is_file()
    assert response["artifacts"]["covariate_capability_context"] == str(path)


def test_load_validates_context_before_delegate(monkeypatch, tmp_path) -> None:
    current = setup(monkeypatch, tmp_path, operation=ProviderOperation.LOAD_PREDICT)
    decision = module.build_request_capability_decision(current)
    module.persist_capability_context(tmp_path, decision)
    called = {"value": False}

    def delegate(payload, runtime=None):
        called["value"] = True
        return {"status": "OK", "metadata": {}, "artifacts": {}}

    monkeypatch.setattr(module, "run_provider_v2_covariates", delegate)
    response = module.run_provider_v2_covariates_guarded({"run_id": "load"})
    assert response["status"] == "OK"
    assert called["value"] is True


def test_load_mismatch_blocks_before_delegate(monkeypatch, tmp_path) -> None:
    current = setup(monkeypatch, tmp_path, operation=ProviderOperation.LOAD_PREDICT)
    decision = module.build_request_capability_decision(current)
    module.persist_capability_context(tmp_path, decision)
    path = tmp_path / module.CAPABILITY_CONTEXT_FILENAME
    text = path.read_text(encoding="utf-8").replace("GBM", "RF")
    path.write_text(text, encoding="utf-8")
    called = {"value": False}
    monkeypatch.setattr(
        module,
        "run_provider_v2_covariates",
        lambda payload, runtime=None: called.update(value=True),
    )
    response = module.run_provider_v2_covariates_guarded({"run_id": "load"})
    assert response["status"] == "ERROR"
    assert response["error"]["code"] == "COVARIATE_CAPABILITY_HASH_MISMATCH"
    assert called["value"] is False


def test_preset_mode_blocks_before_delegate(monkeypatch, tmp_path) -> None:
    current = setup(monkeypatch, tmp_path)
    current.execution_mode = SimpleNamespace(value="preset_automl")
    monkeypatch.setattr(
        module,
        "build_execution_plan",
        lambda value: FakePlan((), {"hyperparameters": {}}),
    )
    called = {"value": False}
    monkeypatch.setattr(
        module,
        "run_provider_v2_covariates",
        lambda payload, runtime=None: called.update(value=True),
    )
    response = module.run_provider_v2_covariates_guarded({"run_id": "preset"})
    assert response["error"]["code"] == "COVARIATES_REQUIRE_EXPLICIT_MODELS"
    assert called["value"] is False


def test_underlying_error_is_preserved(monkeypatch, tmp_path) -> None:
    setup(monkeypatch, tmp_path)
    expected = {"status": "ERROR", "error": {"code": "FIT_FAILED"}}
    monkeypatch.setattr(
        module,
        "run_provider_v2_covariates",
        lambda payload, runtime=None: expected,
    )
    assert module.run_provider_v2_covariates_guarded({"run_id": "fit"}) is expected

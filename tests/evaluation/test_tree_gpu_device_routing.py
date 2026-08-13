from __future__ import annotations

from types import SimpleNamespace

from loto.models import factory
from loto.models.catalog import ModelSpec
from loto.models.factory import RuntimeModel, cuda_device_is_leased


class _CaptureEstimator:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _spec(library: str, class_name: str) -> ModelSpec:
    return ModelSpec(
        model_id=f"test-{library}",
        family="tree",
        library=library,
        task="candidate",
        class_name=class_name,
        capabilities=("probability", "gpu_optional"),
    )


def _estimator(monkeypatch, library: str, class_name: str, *, params=None):
    module = SimpleNamespace(**{class_name: _CaptureEstimator})
    monkeypatch.setattr(factory.importlib, "import_module", lambda name: module)
    return RuntimeModel(_spec(library, class_name), params=params, seed=7)._construct_estimator()


def test_cuda_lease_detection_is_fail_closed(monkeypatch) -> None:
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    assert cuda_device_is_leased() is False

    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
    assert cuda_device_is_leased() is False

    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")
    assert cuda_device_is_leased() is False

    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "3")
    assert cuda_device_is_leased() is True


def test_xgboost_uses_cuda_only_inside_gpu_lease(monkeypatch) -> None:
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    cpu = _estimator(monkeypatch, "xgboost", "XGBClassifier")
    assert cpu.kwargs["random_state"] == 7
    assert cpu.kwargs["n_jobs"] == 1
    assert "device" not in cpu.kwargs

    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "3")
    gpu = _estimator(monkeypatch, "xgboost", "XGBClassifier")
    assert gpu.kwargs["device"] == "cuda"


def test_catboost_uses_logical_gpu_zero_inside_gpu_lease(monkeypatch) -> None:
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    cpu = _estimator(monkeypatch, "catboost", "CatBoostClassifier")
    assert cpu.kwargs["random_seed"] == 7
    assert "task_type" not in cpu.kwargs
    assert "devices" not in cpu.kwargs

    # The outer scheduler exposes exactly one physical GPU through CUDA_VISIBLE_DEVICES.
    # Inside that isolated process the leased device is therefore logical ordinal zero.
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "3")
    gpu = _estimator(monkeypatch, "catboost", "CatBoostClassifier")
    assert gpu.kwargs["task_type"] == "GPU"
    assert gpu.kwargs["devices"] == "0"


def test_explicit_backend_parameters_remain_authoritative(monkeypatch) -> None:
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")

    xgb = _estimator(
        monkeypatch,
        "xgboost",
        "XGBClassifier",
        params={"device": "cpu"},
    )
    assert xgb.kwargs["device"] == "cpu"

    cat = _estimator(
        monkeypatch,
        "catboost",
        "CatBoostClassifier",
        params={"task_type": "CPU"},
    )
    assert cat.kwargs["task_type"] == "CPU"


def test_lightgbm_cuda_is_not_forced_before_build_certification(monkeypatch) -> None:
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    model = _estimator(monkeypatch, "lightgbm", "LGBMClassifier")

    assert model.kwargs["random_state"] == 7
    assert model.kwargs["verbosity"] == -1
    assert "device_type" not in model.kwargs

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from loto.neuralforecast import db_training_evidence_facade as facade_install
from loto.neuralforecast.runtime_evidence import formal_training_cuda
from loto.neuralforecast.training_worker_evidence import (
    TrainingWorkerEvidenceMixin,
    build_training_worker_callback,
    training_evidence_auto_class,
)


def _run_hooks(callback, *, device: str = "cpu") -> None:
    trainer = SimpleNamespace(
        strategy=SimpleNamespace(root_device=device),
        global_rank=0,
        local_rank=0,
        world_size=1,
    )
    module = SimpleNamespace(device=device)
    callback.on_fit_start(trainer, module)
    callback.on_train_start(trainer, module)
    callback.on_train_batch_end(trainer, module, None, None, 0)
    callback.on_train_end(trainer, module)


def test_cpu_callback_is_formal_training_proof_but_not_cuda() -> None:
    callback = build_training_worker_callback(
        backend="optuna",
        model_name="AutoDLinear",
        model_id="nf-auto-dlinear",
        require_gpu=False,
        runtime_snapshot_fn=lambda trainer, module: {
            "pid": __import__("os").getpid(),
            "parameter_device": "cpu",
            "trainer_root_device": "cpu",
            "cuda_memory_allocated": 0,
            "cuda_memory_reserved": 0,
            "cuda_peak_memory_allocated": 0,
        },
        gpu_snapshot_fn=lambda: {
            "pid": __import__("os").getpid(),
            "gpu_pid_verified": False,
        },
    )
    _run_hooks(callback)
    evidence = callback.evidence()
    assert evidence.status == "PASS"
    assert evidence.formal_training_proof is True
    assert evidence.cuda_execution_evidence is False
    assert evidence.cpu_fallback is False
    assert formal_training_cuda(evidence.model_dump(mode="json")) is False


def test_gpu_callback_requires_device_vram_and_same_pid() -> None:
    callback = build_training_worker_callback(
        backend="ray",
        model_name="AutoDLinear",
        model_id="nf-auto-dlinear",
        require_gpu=True,
        runtime_snapshot_fn=lambda trainer, module: {
            "pid": __import__("os").getpid(),
            "parameter_device": "cuda:0",
            "trainer_root_device": "cuda:0",
            "cuda_memory_allocated": 1024,
            "cuda_memory_reserved": 2048,
            "cuda_peak_memory_allocated": 4096,
        },
        gpu_snapshot_fn=lambda: {
            "pid": __import__("os").getpid(),
            "gpu_pid_verified": True,
        },
    )
    _run_hooks(callback, device="cuda:0")
    evidence = callback.evidence().model_dump(mode="json")
    assert formal_training_cuda(evidence) is True
    assert evidence["failed_checks"] == []
    assert evidence["runtime_pid_match"] is True
    assert evidence["gpu_pid_match"] is True


@pytest.mark.parametrize(
    ("runtime", "gpu", "failure"),
    [
        ({"parameter_device": "cpu"}, {"gpu_pid_verified": True}, "cuda_device"),
        (
            {"parameter_device": "cuda:0", "cuda_peak_memory_allocated": 0},
            {"gpu_pid_verified": True},
            "positive_vram",
        ),
        (
            {"parameter_device": "cuda:0", "cuda_peak_memory_allocated": 10},
            {"gpu_pid_verified": False},
            "gpu_pid",
        ),
    ],
)
def test_gpu_callback_fails_closed(runtime, gpu, failure) -> None:
    callback = build_training_worker_callback(
        backend="ray",
        model_name="AutoDLinear",
        model_id="nf-auto-dlinear",
        require_gpu=True,
        runtime_snapshot_fn=lambda trainer, module: {
            "pid": __import__("os").getpid(),
            **runtime,
        },
        gpu_snapshot_fn=lambda: {
            "pid": __import__("os").getpid(),
            **gpu,
        },
    )
    _run_hooks(callback)
    evidence = callback.evidence()
    assert evidence.status == "FAIL"
    assert failure in evidence.failed_checks
    assert evidence.cpu_fallback is True


def test_formal_training_cuda_rejects_forged_legacy_dict() -> None:
    assert (
        formal_training_cuda({"formal_training_proof": True, "cuda_execution_evidence": True})
        is False
    )


def test_formal_training_cuda_rejects_worker_pid_mismatch() -> None:
    callback = build_training_worker_callback(
        backend="ray",
        model_name="AutoDLinear",
        model_id="nf-auto-dlinear",
        require_gpu=True,
        runtime_snapshot_fn=lambda trainer, module: {
            "pid": __import__("os").getpid(),
            "parameter_device": "cuda:0",
            "cuda_peak_memory_allocated": 1024,
        },
        gpu_snapshot_fn=lambda: {
            "pid": __import__("os").getpid(),
            "gpu_pid_verified": True,
        },
    )
    _run_hooks(callback, device="cuda:0")
    evidence = callback.evidence().model_dump(mode="json")
    evidence["gpu_process"]["pid"] = evidence["worker_pid"] + 1
    assert formal_training_cuda(evidence) is False


def test_extract_training_evidence_finds_final_inner_model() -> None:
    from loto.neuralforecast.runtime_evidence import extract_training_evidence

    payload = {"schema_version": "1.0.0", "status": "PASS"}
    inner = SimpleNamespace(training_runtime_evidence=payload)
    wrapper = SimpleNamespace(model=inner)
    assert extract_training_evidence(SimpleNamespace(models=[wrapper])) == payload


def test_mixin_attaches_final_fit_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    class Base:
        def _fit_model(self, **kwargs):
            callback = kwargs["config"]["callbacks"][-1]
            _run_hooks(callback)
            return SimpleNamespace()

    class Instrumented(TrainingWorkerEvidenceMixin, Base):
        training_evidence_backend = "optuna"
        training_evidence_model_name = "AutoDLinear"
        training_evidence_model_id = "nf-auto-dlinear"
        training_evidence_require_gpu = False

    model = Instrumented()._fit_model(
        cls_model=object,
        config={},
        dataset=None,
        val_size=1,
        test_size=0,
    )
    assert model.training_runtime_evidence["status"] == "PASS"
    assert model.runtime_training_evidence == model.training_runtime_evidence


def test_dynamic_class_is_cached_and_pickle_addressable() -> None:
    class AutoModel:
        pass

    first = training_evidence_auto_class(AutoModel)
    second = training_evidence_auto_class(AutoModel)
    assert first is second
    assert getattr(sys.modules[first.__module__], first.__name__) is first


def test_database_facade_patches_class_and_configures_model(monkeypatch) -> None:
    auto_module = ModuleType("neuralforecast.auto")

    class AutoDLinear:
        pass

    auto_module.AutoDLinear = AutoDLinear
    package = ModuleType("neuralforecast")
    package.auto = auto_module
    monkeypatch.setitem(sys.modules, "neuralforecast", package)
    monkeypatch.setitem(sys.modules, "neuralforecast.auto", auto_module)

    context = SimpleNamespace(
        config=SimpleNamespace(gpus=1, require_gpu_execution=None),
        spec=SimpleNamespace(model_id="nf-auto-dlinear"),
    )
    facade = ModuleType("fake_facade")
    facade._CONTEXT = SimpleNamespace(get=lambda: context)

    def original_construct(plan):
        return auto_module.AutoDLinear()

    facade._construct_interceptor = original_construct
    facade._construct_auto_hint = lambda config, panel: (object(), panel, {}, {})
    facade_install.install(facade)
    result = facade._construct_interceptor(
        SimpleNamespace(model_name="AutoDLinear", backend="optuna")
    )
    assert isinstance(result, TrainingWorkerEvidenceMixin)
    assert result.training_evidence_require_gpu is True
    assert result.training_evidence_model_id == "nf-auto-dlinear"
    assert auto_module.AutoDLinear is AutoDLinear


def test_callback_captures_only_first_training_batch() -> None:
    calls = {"runtime": 0, "gpu": 0}

    def runtime_snapshot(trainer, module):
        calls["runtime"] += 1
        return {
            "pid": __import__("os").getpid(),
            "parameter_device": "cpu",
            "trainer_root_device": "cpu",
        }

    def gpu_snapshot():
        calls["gpu"] += 1
        return {
            "pid": __import__("os").getpid(),
            "gpu_pid_verified": False,
        }

    callback = build_training_worker_callback(
        backend="optuna",
        model_name="AutoDLinear",
        model_id="nf-auto-dlinear",
        require_gpu=False,
        runtime_snapshot_fn=runtime_snapshot,
        gpu_snapshot_fn=gpu_snapshot,
    )
    trainer = SimpleNamespace(strategy=SimpleNamespace(root_device="cpu"))
    module = SimpleNamespace(device="cpu")
    callback.on_fit_start(trainer, module)
    callback.on_train_start(trainer, module)
    callback.on_train_batch_end(trainer, module, None, None, 0)
    callback.on_train_batch_end(trainer, module, None, None, 1)
    callback.on_train_end(trainer, module)
    assert calls == {"runtime": 4, "gpu": 4}


def test_database_facade_instruments_autohint(monkeypatch) -> None:
    auto_module = ModuleType("neuralforecast.auto")

    class AutoHINT:
        pass

    auto_module.AutoHINT = AutoHINT
    package = ModuleType("neuralforecast")
    package.auto = auto_module
    monkeypatch.setitem(sys.modules, "neuralforecast", package)
    monkeypatch.setitem(sys.modules, "neuralforecast.auto", auto_module)

    context = SimpleNamespace(
        config=SimpleNamespace(gpus=1, require_gpu_execution=True),
        spec=SimpleNamespace(model_id="nf-auto-hint"),
    )
    facade = ModuleType("fake_facade")
    facade._CONTEXT = SimpleNamespace(get=lambda: context)
    facade._construct_interceptor = lambda plan: plan

    def original_hint(config, panel):
        return auto_module.AutoHINT(), panel, {}, {}

    facade._construct_auto_hint = original_hint
    facade_install.install(facade)
    model, *_ = facade._construct_auto_hint(SimpleNamespace(), object())
    assert isinstance(model, TrainingWorkerEvidenceMixin)
    assert model.training_evidence_backend == "ray"
    assert model.training_evidence_model_id == "nf-auto-hint"
    assert model.training_evidence_require_gpu is True
    assert auto_module.AutoHINT is AutoHINT


def test_database_facade_install_is_idempotent() -> None:
    facade = ModuleType("fake_facade")
    facade._CONTEXT = SimpleNamespace(get=lambda: None)
    facade._construct_interceptor = lambda plan: plan
    facade._construct_auto_hint = lambda config, panel: (config, panel)
    facade_install.install(facade)
    first = facade._construct_interceptor
    facade_install.install(facade)
    assert facade._construct_interceptor is first

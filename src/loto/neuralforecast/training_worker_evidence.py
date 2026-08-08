"""Capture fail-closed training-worker evidence inside Lightning training hooks."""

from __future__ import annotations

import os
import socket
from datetime import UTC, datetime
from threading import RLock
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field


class TrainingWorkerEvidence(BaseModel):
    """Serializable evidence produced in the process that executed model training."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = "1.0.0"
    source: Literal["pytorch_lightning_training_callback"] = "pytorch_lightning_training_callback"
    status: Literal["PASS", "FAIL"]
    backend: Literal["ray", "optuna"]
    model_name: str = Field(min_length=1)
    model_id: str | None = None
    captured_at_utc: str
    worker_pid: int
    hostname: str
    require_gpu: bool
    observed_fit_start: bool
    observed_train_start: bool
    observed_train_batch: bool
    observed_train_end: bool
    runtime: dict[str, Any] = Field(default_factory=dict)
    gpu_process: dict[str, Any] = Field(default_factory=dict)
    device_cuda: bool
    vram_positive: bool
    gpu_pid_verified: bool
    runtime_pid_match: bool
    gpu_pid_match: bool
    cuda_execution_evidence: bool
    formal_training_proof: bool
    cpu_fallback: bool
    failed_checks: tuple[str, ...] = ()


def _safe_gpu_process_snapshot() -> dict[str, Any]:
    try:
        from loto.auto_campaign.runtime import gpu_process_snapshot

        return dict(gpu_process_snapshot())
    except Exception as exc:  # runtime evidence must survive missing nvidia-smi
        return {
            "pid": os.getpid(),
            "gpu_pid_verified": False,
            "rows": [],
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def _runtime_snapshot(trainer: Any, module: Any) -> dict[str, Any]:
    try:
        import torch
    except ImportError:
        torch = None

    root_device = getattr(getattr(trainer, "strategy", None), "root_device", None)
    module_device = getattr(module, "device", None)
    payload: dict[str, Any] = {
        "pid": os.getpid(),
        "parameter_device": None if module_device is None else str(module_device),
        "trainer_root_device": None if root_device is None else str(root_device),
        "global_rank": getattr(trainer, "global_rank", None),
        "local_rank": getattr(trainer, "local_rank", None),
        "world_size": getattr(trainer, "world_size", None),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "cuda_available": False,
        "cuda_memory_allocated": 0,
        "cuda_memory_reserved": 0,
        "cuda_peak_memory_allocated": 0,
    }
    if torch is None:
        return payload
    try:
        payload["cuda_available"] = bool(torch.cuda.is_available())
        if payload["cuda_available"]:
            payload.update(
                {
                    "cuda_current_device": int(torch.cuda.current_device()),
                    "cuda_memory_allocated": int(torch.cuda.memory_allocated()),
                    "cuda_memory_reserved": int(torch.cuda.memory_reserved()),
                    "cuda_peak_memory_allocated": int(torch.cuda.max_memory_allocated()),
                }
            )
    except Exception as exc:
        payload["cuda_snapshot_error"] = f"{type(exc).__name__}: {exc}"
    return payload


def _cuda_device(runtime: dict[str, Any]) -> bool:
    return any(
        str(runtime.get(key) or "").lower().startswith("cuda")
        for key in ("parameter_device", "trainer_root_device")
    )


def _positive_vram(runtime: dict[str, Any]) -> bool:
    return any(
        int(runtime.get(key) or 0) > 0
        for key in (
            "cuda_memory_allocated",
            "cuda_memory_reserved",
            "cuda_peak_memory_allocated",
        )
    )


class _Recorder:
    def __init__(
        self,
        *,
        backend: str,
        model_name: str,
        model_id: str | None,
        require_gpu: bool,
        runtime_snapshot_fn: Callable[[Any, Any], dict[str, Any]],
        gpu_snapshot_fn: Callable[[], dict[str, Any]],
    ) -> None:
        self.backend = backend
        self.model_name = model_name
        self.model_id = model_id
        self.require_gpu = require_gpu
        self.runtime_snapshot_fn = runtime_snapshot_fn
        self.gpu_snapshot_fn = gpu_snapshot_fn
        self.observed_fit_start = False
        self.observed_train_start = False
        self.observed_train_batch = False
        self.observed_train_end = False
        self.runtime: dict[str, Any] = {}
        self.gpu_process: dict[str, Any] = {}
        self.callback_error: str | None = None

    def capture(self, trainer: Any, module: Any) -> None:
        try:
            current = self.runtime_snapshot_fn(trainer, module)
            for key, value in current.items():
                if key.startswith("cuda_memory_") or key == "cuda_peak_memory_allocated":
                    self.runtime[key] = max(int(self.runtime.get(key) or 0), int(value or 0))
                else:
                    self.runtime[key] = value
            gpu = self.gpu_snapshot_fn()
            if gpu.get("gpu_pid_verified") is True or not self.gpu_process:
                self.gpu_process = gpu
        except Exception as exc:
            self.callback_error = f"{type(exc).__name__}: {exc}"

    def result(self) -> TrainingWorkerEvidence:
        device_cuda = _cuda_device(self.runtime)
        vram_positive = _positive_vram(self.runtime)
        worker_pid = os.getpid()
        runtime_pid_match = self.runtime.get("pid") == worker_pid
        gpu_pid_match = self.gpu_process.get("pid") == worker_pid
        gpu_pid_verified = bool(self.gpu_process.get("gpu_pid_verified") is True and gpu_pid_match)
        cuda_execution = bool(
            device_cuda and vram_positive and gpu_pid_verified and runtime_pid_match
        )
        failed: list[str] = []
        if not self.observed_fit_start:
            failed.append("fit_start_hook")
        if not self.observed_train_start:
            failed.append("train_start_hook")
        if not self.observed_train_batch:
            failed.append("train_batch_hook")
        if not self.observed_train_end:
            failed.append("train_end_hook")
        if self.callback_error:
            failed.append("callback_capture")
        if not runtime_pid_match:
            failed.append("runtime_worker_pid")
        if self.require_gpu:
            if not device_cuda:
                failed.append("cuda_device")
            if not vram_positive:
                failed.append("positive_vram")
            if not gpu_pid_match:
                failed.append("gpu_worker_pid")
            if not gpu_pid_verified:
                failed.append("gpu_pid")
        formal = not failed
        return TrainingWorkerEvidence(
            status="PASS" if formal else "FAIL",
            backend=self.backend,
            model_name=self.model_name,
            model_id=self.model_id,
            captured_at_utc=datetime.now(UTC).isoformat(),
            worker_pid=worker_pid,
            hostname=socket.gethostname(),
            require_gpu=self.require_gpu,
            observed_fit_start=self.observed_fit_start,
            observed_train_start=self.observed_train_start,
            observed_train_batch=self.observed_train_batch,
            observed_train_end=self.observed_train_end,
            runtime=self.runtime,
            gpu_process=self.gpu_process,
            device_cuda=device_cuda,
            vram_positive=vram_positive,
            gpu_pid_verified=gpu_pid_verified,
            runtime_pid_match=runtime_pid_match,
            gpu_pid_match=gpu_pid_match,
            cuda_execution_evidence=cuda_execution,
            formal_training_proof=formal,
            cpu_fallback=bool(self.require_gpu and not cuda_execution),
            failed_checks=tuple(failed),
        )


def build_training_worker_callback(
    *,
    backend: str,
    model_name: str,
    model_id: str | None,
    require_gpu: bool,
    runtime_snapshot_fn: Callable[[Any, Any], dict[str, Any]] = _runtime_snapshot,
    gpu_snapshot_fn: Callable[[], dict[str, Any]] = _safe_gpu_process_snapshot,
):
    """Create a Lightning callback lazily so dependency-light imports still work."""

    from pytorch_lightning.callbacks import Callback

    recorder = _Recorder(
        backend=backend,
        model_name=model_name,
        model_id=model_id,
        require_gpu=require_gpu,
        runtime_snapshot_fn=runtime_snapshot_fn,
        gpu_snapshot_fn=gpu_snapshot_fn,
    )

    class TrainingWorkerCallback(Callback):
        def on_fit_start(self, trainer: Any, pl_module: Any) -> None:
            recorder.observed_fit_start = True
            recorder.capture(trainer, pl_module)

        def on_train_start(self, trainer: Any, pl_module: Any) -> None:
            recorder.observed_train_start = True
            recorder.capture(trainer, pl_module)

        def on_train_batch_end(
            self,
            trainer: Any,
            pl_module: Any,
            outputs: Any,
            batch: Any,
            batch_idx: int,
        ) -> None:
            if not recorder.observed_train_batch:
                recorder.observed_train_batch = True
                recorder.capture(trainer, pl_module)

        def on_train_end(self, trainer: Any, pl_module: Any) -> None:
            recorder.observed_train_end = True
            recorder.capture(trainer, pl_module)

        def evidence(self) -> TrainingWorkerEvidence:
            return recorder.result()

    return TrainingWorkerCallback()


class TrainingWorkerEvidenceMixin:
    """Inject the evidence callback into every BaseAuto trial and final refit."""

    training_evidence_backend: str = "unknown"
    training_evidence_model_name: str = "unknown"
    training_evidence_model_id: str | None = None
    training_evidence_require_gpu: bool = False

    def _fit_model(
        self,
        cls_model: type,
        config: dict[str, Any],
        dataset: Any,
        val_size: int,
        test_size: int,
        distributed_config: Any = None,
    ):
        configured = dict(config)
        callback = build_training_worker_callback(
            backend=str(self.training_evidence_backend),
            model_name=str(self.training_evidence_model_name),
            model_id=self.training_evidence_model_id,
            require_gpu=bool(self.training_evidence_require_gpu),
        )
        callbacks = list(configured.get("callbacks") or [])
        callbacks.append(callback)
        configured["callbacks"] = callbacks
        model = super()._fit_model(
            cls_model=cls_model,
            config=configured,
            dataset=dataset,
            val_size=val_size,
            test_size=test_size,
            distributed_config=distributed_config,
        )
        evidence = callback.evidence().model_dump(mode="json")
        setattr(model, "training_runtime_evidence", evidence)
        setattr(model, "runtime_training_evidence", evidence)
        return model


_CLASS_CACHE: dict[type, type] = {}
_CLASS_LOCK = RLock()


def training_evidence_auto_class(auto_cls: type) -> type:
    """Return a stable pickle-addressable AutoModel subclass."""

    with _CLASS_LOCK:
        cached = _CLASS_CACHE.get(auto_cls)
        if cached is not None:
            return cached
        name = f"TrainingEvidence{auto_cls.__name__}"
        created = type(
            name,
            (TrainingWorkerEvidenceMixin, auto_cls),
            {"__module__": __name__, "__qualname__": name},
        )
        globals()[name] = created
        _CLASS_CACHE[auto_cls] = created
        return created


def configure_training_evidence(
    model: Any,
    *,
    backend: str,
    model_name: str,
    model_id: str | None,
    require_gpu: bool,
) -> Any:
    model.training_evidence_backend = backend
    model.training_evidence_model_name = model_name
    model.training_evidence_model_id = model_id
    model.training_evidence_require_gpu = require_gpu
    return model


def _register_runtime_auto_classes() -> None:
    try:
        import inspect

        import neuralforecast.auto as auto_module
        from neuralforecast.common._base_auto import BaseAuto
    except ImportError:
        return
    for exported_name in getattr(auto_module, "__all__", ()):
        value = getattr(auto_module, exported_name, None)
        if inspect.isclass(value) and value is not BaseAuto and issubclass(value, BaseAuto):
            training_evidence_auto_class(value)


_register_runtime_auto_classes()

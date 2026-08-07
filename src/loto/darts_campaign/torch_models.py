from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .argument_validator import classify_arguments
from .protocol import GameGeometry
from .timeseries_adapter import build_position_local, to_darts_local

TORCH_MODEL_IDENTITIES = (
    "NBEATSModel",
    "NHiTSModel",
    "TCNModel",
    "TFTModel",
    "DLinearModel",
    "NLinearModel",
    "TiDEModel",
    "TSMixerModel",
    "TransformerModel",
    "RNNModel",
)


class TorchParallelPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outer_workers: int = Field(default=8, ge=1, le=64)
    max_gpu_jobs: int = Field(default=1, ge=1, le=8)
    max_cpu_jobs: int = Field(default=7, ge=0, le=64)

    @model_validator(mode="after")
    def validate_policy(self) -> TorchParallelPolicy:
        if self.max_gpu_jobs != 1:
            raise ValueError("P7 requires max_gpu_jobs=1")
        if self.max_gpu_jobs + self.max_cpu_jobs > self.outer_workers:
            raise ValueError("declared concurrency exceeds outer_workers")
        return self


class TorchDeviceContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_accelerator: Literal["cpu", "gpu"] = "gpu"
    devices: tuple[int, ...] = (0,)
    allow_cpu_fallback: bool = False
    require_gpu_pid: bool = True
    require_vram_evidence: bool = True

    @field_validator("devices")
    @classmethod
    def normalize_devices(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        value = tuple(dict.fromkeys(value))
        if any(item < 0 for item in value):
            raise ValueError("device indexes must be non-negative")
        return value

    @model_validator(mode="after")
    def validate_device(self) -> TorchDeviceContract:
        if self.requested_accelerator == "gpu" and len(self.devices) != 1:
            raise ValueError("GPU execution requires exactly one device")
        if self.requested_accelerator == "cpu" and self.devices:
            raise ValueError("CPU execution must not declare CUDA devices")
        if self.allow_cpu_fallback:
            raise ValueError("P7 forbids CPU fallback")
        return self

    def trainer_kwargs(self) -> dict[str, Any]:
        devices: int | list[int] = list(self.devices) if self.devices else 1
        return {"accelerator": self.requested_accelerator, "devices": devices}


RuntimeObjectResolver = Callable[[str, str], Any]


class TorchTrainingContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_chunk_length: int = Field(ge=1, le=8192)
    output_chunk_length: int = Field(default=1, ge=1, le=512)
    output_chunk_shift: int = Field(default=0, ge=0, le=512)
    n_epochs: int = Field(default=1, ge=1, le=10000)
    batch_size: int = Field(default=32, ge=1, le=65536)
    random_state: int = 1
    save_checkpoints: bool = True
    force_reset: bool = True
    optimizer_kwargs: dict[str, Any] = Field(default_factory=dict)
    lr_scheduler_cls_id: str | None = None
    lr_scheduler_kwargs: dict[str, Any] = Field(default_factory=dict)
    loss_fn_id: str | None = None
    likelihood_id: str | None = None
    torch_metrics: tuple[str, ...] = ()
    add_encoders: dict[str, Any] = Field(default_factory=dict)
    pl_trainer_extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_training(self) -> TorchTrainingContract:
        protected = {"accelerator", "devices"}
        overlap = sorted(protected & set(self.pl_trainer_extra))
        if overlap:
            raise ValueError(f"pl_trainer_extra cannot override {overlap}")
        if self.lr_scheduler_kwargs and self.lr_scheduler_cls_id is None:
            raise ValueError("lr_scheduler_kwargs require lr_scheduler_cls_id")
        return self

    def constructor_args(
        self,
        device: TorchDeviceContract,
        resolver: RuntimeObjectResolver | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "input_chunk_length": self.input_chunk_length,
            "output_chunk_length": self.output_chunk_length,
            "output_chunk_shift": self.output_chunk_shift,
            "n_epochs": self.n_epochs,
            "batch_size": self.batch_size,
            "optimizer_kwargs": dict(self.optimizer_kwargs),
            "random_state": self.random_state,
            "pl_trainer_kwargs": {
                **device.trainer_kwargs(),
                **self.pl_trainer_extra,
            },
            "save_checkpoints": self.save_checkpoints,
            "force_reset": self.force_reset,
        }
        identities = {
            "lr_scheduler_cls": self.lr_scheduler_cls_id,
            "loss_fn": self.loss_fn_id,
            "likelihood": self.likelihood_id,
        }
        for kind, identity in identities.items():
            if identity is not None:
                if resolver is None:
                    raise ValueError(f"{kind} identity requires runtime object resolver")
                payload[kind] = resolver(kind, identity)
        if self.lr_scheduler_cls_id is not None:
            payload["lr_scheduler_kwargs"] = dict(self.lr_scheduler_kwargs)
        if self.torch_metrics:
            if resolver is None:
                raise ValueError("torch_metrics require runtime object resolver")
            payload["torch_metrics"] = [
                resolver("torch_metric", item) for item in self.torch_metrics
            ]
        if self.add_encoders:
            payload["add_encoders"] = dict(self.add_encoders)
        return payload


class TorchModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    public_name: str
    model_args: dict[str, Any] = Field(default_factory=dict)
    min_train_size: int = Field(default=8, ge=2, le=1000000)

    @model_validator(mode="after")
    def validate_identity(self) -> TorchModelConfig:
        if self.public_name not in TORCH_MODEL_IDENTITIES:
            raise ValueError(f"unsupported Torch model: {self.public_name}")
        return self


class TorchCampaignConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    run_id: str = Field(min_length=1)
    models: tuple[TorchModelConfig, ...]
    training: TorchTrainingContract
    device: TorchDeviceContract = Field(default_factory=TorchDeviceContract)
    parallel: TorchParallelPolicy = Field(default_factory=TorchParallelPolicy)
    series_layout: Literal["position_local", "position_global_sequence"]
    horizon: int = Field(default=1, ge=1, le=512)
    fit_args: dict[str, Any] = Field(default_factory=dict)
    predict_args: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_campaign(self) -> TorchCampaignConfig:
        names = [item.public_name for item in self.models]
        if not names or len(names) != len(set(names)):
            raise ValueError("Torch model identities must be non-empty and unique")
        if self.horizon > self.training.output_chunk_length:
            raise ValueError("horizon must not exceed output_chunk_length")
        return self


class TorchRuntimeObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    torch_cuda_available: bool
    requested_accelerator: Literal["cpu", "gpu"]
    effective_accelerator: Literal["cpu", "gpu"]
    model_parameter_devices: tuple[str, ...]
    prediction_device: str
    process_pid: int = Field(ge=1)
    gpu_pid: int | None = Field(default=None, ge=1)
    device_index: int | None = Field(default=None, ge=0)
    vram_before_bytes: int | None = Field(default=None, ge=0)
    vram_peak_bytes: int | None = Field(default=None, ge=0)
    vram_after_bytes: int | None = Field(default=None, ge=0)
    cuda_allocated_bytes: int | None = Field(default=None, ge=0)
    cuda_reserved_bytes: int | None = Field(default=None, ge=0)
    cpu_fallback_reason: str | None = None


@dataclass(frozen=True)
class TorchModelResult:
    model_name: str
    status: str
    predictions: tuple[tuple[float, ...], ...] | None
    failure_class: str | None
    message: str | None
    argument_ledger: tuple[dict[str, Any], ...]
    device_certifications: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]


RuntimeProbe = Callable[[str, Any, Any, int | None], TorchRuntimeObservation]


class DeviceCertificationError(RuntimeError):
    def __init__(self, record: dict[str, Any]) -> None:
        self.record = record
        super().__init__(f"{record['failure_class']}: {record['message']}")


def build_parallel_plan(policy: TorchParallelPolicy) -> dict[str, Any]:
    return {
        "outer_workers": policy.outer_workers,
        "max_gpu_jobs": policy.max_gpu_jobs,
        "max_cpu_jobs": policy.max_cpu_jobs,
        "gpu_queue_serialized": policy.max_gpu_jobs == 1,
    }


def certify_device_use(
    contract: TorchDeviceContract,
    observation: TorchRuntimeObservation,
) -> dict[str, Any]:
    evidence = observation.model_dump(mode="json")
    failure: tuple[str, str] | None = None
    if observation.requested_accelerator != contract.requested_accelerator:
        status = "RUNTIME_EVIDENCE_MISMATCH"
        failure = ("RUNTIME_EVIDENCE_MISMATCH", "requested accelerator mismatch")
    elif contract.requested_accelerator == "cpu":
        used = observation.effective_accelerator == "cpu"
        used &= all(item.lower().startswith("cpu") for item in observation.model_parameter_devices)
        used &= observation.prediction_device.lower().startswith("cpu")
        if not used:
            failure = ("DEVICE_MISMATCH", "CPU request used a non-CPU device")
        status = "CPU_REQUESTED_AND_USED" if used else "CPU_DEVICE_MISMATCH"
    else:
        used = observation.torch_cuda_available
        used &= observation.effective_accelerator == "gpu"
        used &= bool(observation.model_parameter_devices)
        used &= all(
            item.lower().startswith("cuda")
            for item in observation.model_parameter_devices
        )
        used &= observation.prediction_device.lower().startswith("cuda")
        status = "GPU_REQUESTED_AND_USED"
        if not used:
            status = "GPU_REQUESTED_BUT_CPU_FALLBACK"
            if not contract.allow_cpu_fallback:
                failure = (
                    "CPU_FALLBACK_REJECTED",
                    observation.cpu_fallback_reason or "GPU evidence is incomplete",
                )
        if failure is None and contract.require_gpu_pid and observation.gpu_pid is None:
            failure = ("GPU_PID_MISSING", "GPU PID evidence is required")
            status = "GPU_EVIDENCE_INCOMPLETE"
        memory = (
            observation.vram_before_bytes,
            observation.vram_peak_bytes,
            observation.vram_after_bytes,
            observation.cuda_allocated_bytes,
            observation.cuda_reserved_bytes,
        )
        if failure is None and contract.require_vram_evidence and any(
            item is None for item in memory
        ):
            failure = ("VRAM_EVIDENCE_MISSING", "VRAM/CUDA memory evidence is required")
            status = "GPU_EVIDENCE_INCOMPLETE"
        if failure is None and contract.require_vram_evidence:
            assert observation.vram_peak_bytes is not None
            assert observation.vram_before_bytes is not None
            assert observation.vram_after_bytes is not None
            if observation.vram_peak_bytes < max(
                observation.vram_before_bytes,
                observation.vram_after_bytes,
            ):
                failure = ("VRAM_EVIDENCE_INVALID", "VRAM peak is inconsistent")
                status = "GPU_EVIDENCE_INVALID"
    return {
        "status": status,
        "passed": failure is None,
        "failure_class": None if failure is None else failure[0],
        "message": None if failure is None else failure[1],
        "evidence": evidence,
    }


def _array(prediction: Any) -> np.ndarray:
    values = prediction.values() if hasattr(prediction, "values") else prediction
    array = np.asarray(values, dtype=float).reshape(-1)
    if not np.isfinite(array).all():
        raise ValueError("prediction contains NaN or Inf")
    return array


def _normalize(predictions: Any, positions: int, horizon: int) -> tuple[tuple[float, ...], ...]:
    blocks = list(predictions) if isinstance(predictions, (list, tuple)) else [predictions]
    if len(blocks) != positions:
        raise ValueError("prediction position count mismatch")
    output = []
    for block in blocks:
        array = _array(block)
        if array.size != horizon:
            raise ValueError("prediction horizon mismatch")
        output.append(tuple(float(item) for item in array))
    return tuple(output)


def _ledger(items: list[Any]) -> tuple[dict[str, Any], ...]:
    return tuple(item.model_dump(mode="json") for item in items)


def _run_model(
    name: str,
    model_cls: Any,
    constructor: Mapping[str, Any],
    config: TorchCampaignConfig,
    series: list[Any],
    probe: RuntimeProbe,
) -> tuple[
    tuple[tuple[float, ...], ...],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
]:
    ledgers: list[Any] = []
    certs: list[dict[str, Any]] = []
    predictions: list[Any] = []

    def certify(model: Any, prediction: Any, position: int | None) -> None:
        record = certify_device_use(config.device, probe(name, model, prediction, position))
        record = {"position": position, **record}
        certs.append(record)
        if not record["passed"]:
            raise DeviceCertificationError(record)

    if config.series_layout == "position_local":
        for position, item in enumerate(series):
            effective, current = classify_arguments(model_cls, constructor)
            ledgers.extend(current)
            model = model_cls(**effective)
            effective, current = classify_arguments(model.fit, config.fit_args)
            ledgers.extend(current)
            model.fit(item, **effective)
            effective, current = classify_arguments(model.predict, config.predict_args)
            ledgers.extend(current)
            prediction = model.predict(config.horizon, **effective)
            certify(model, prediction, position)
            predictions.append(prediction)
    else:
        effective, current = classify_arguments(model_cls, constructor)
        ledgers.extend(current)
        model = model_cls(**effective)
        effective, current = classify_arguments(model.fit, config.fit_args)
        ledgers.extend(current)
        model.fit(series, **effective)
        request = {"series": series, **config.predict_args}
        effective, current = classify_arguments(model.predict, request)
        ledgers.extend(current)
        predictions = model.predict(config.horizon, **effective)
        certify(model, predictions, None)
    return _normalize(predictions, len(series), config.horizon), _ledger(ledgers), tuple(certs)


def run_torch_matrix(
    config: TorchCampaignConfig,
    frame: pd.DataFrame,
    geometry: GameGeometry,
    *,
    models_module: Any | None = None,
    timeseries_cls: Any | None = None,
    runtime_probe: RuntimeProbe | None = None,
    object_resolver: RuntimeObjectResolver | None = None,
) -> tuple[TorchModelResult, ...]:
    if runtime_probe is None:
        raise ValueError("runtime_probe is required for P7 certification")
    payload = build_position_local(frame, geometry)
    if len(frame) < config.training.input_chunk_length + config.horizon:
        raise ValueError("training history is shorter than input chunk plus horizon")
    series = to_darts_local(payload, timeseries_cls)
    try:
        module = models_module or importlib.import_module("darts.models")
    except (ImportError, ModuleNotFoundError) as exc:
        message = f"{type(exc).__name__}: {exc}"
        return tuple(
            TorchModelResult(
                item.public_name,
                "FAILED",
                None,
                "DEPENDENCY_MISSING",
                message,
                (),
                (),
                {"series_layout": config.series_layout},
            )
            for item in config.models
        )
    base = config.training.constructor_args(config.device, object_resolver)
    results: list[TorchModelResult] = []
    for item in config.models:
        try:
            if len(frame) < item.min_train_size:
                raise ValueError("training history is below model minimum")
            model_cls = getattr(module, item.public_name)
            predictions, ledger, certs = _run_model(
                item.public_name,
                model_cls,
                {**base, **item.model_args},
                config,
                series,
                runtime_probe,
            )
            results.append(
                TorchModelResult(
                    item.public_name,
                    "SUCCEEDED",
                    predictions,
                    None,
                    None,
                    ledger,
                    certs,
                    {
                        "series_layout": config.series_layout,
                        "parallel_plan": build_parallel_plan(config.parallel),
                        "effective_trainer_kwargs": base["pl_trainer_kwargs"],
                    },
                )
            )
        except (AttributeError, ImportError, ModuleNotFoundError) as exc:
            failure = "DEPENDENCY_MISSING"
            certs = ()
            message = f"{type(exc).__name__}: {exc}"
        except DeviceCertificationError as exc:
            failure = exc.record["failure_class"]
            certs = (exc.record,)
            message = str(exc)
        except ValueError as exc:
            failure = "INVALID_REQUEST"
            certs = ()
            message = str(exc)
        except Exception as exc:
            failure = "FIT_OR_PREDICT_FAILED"
            certs = ()
            message = f"{type(exc).__name__}: {exc}"
        if len(results) == 0 or results[-1].model_name != item.public_name:
            results.append(
                TorchModelResult(
                    item.public_name,
                    "FAILED",
                    None,
                    failure,
                    message,
                    (),
                    certs,
                    {"series_layout": config.series_layout},
                )
            )
    return tuple(results)

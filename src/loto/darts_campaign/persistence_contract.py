from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections.abc import Callable, Mapping
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .torch_models import TorchRuntimeObservation

P11_FAMILIES = (
    "local",
    "regression",
    "torch",
    "foundation",
    "ensemble",
    "conformal",
)
PersistenceMethod = Literal[
    "manual",
    "manual_clean",
    "checkpoint_best",
    "checkpoint_last",
    "weights",
    "cross_device_cpu",
    "cross_device_cuda",
]


class PersistenceContractError(ValueError):
    """Raised when persistence evidence violates a fail-closed contract."""


class TemporalPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    values: tuple[tuple[float, ...], ...]

    @model_validator(mode="after")
    def validate_values(self) -> TemporalPrediction:
        array = self.array()
        if array.ndim != 2 or array.size == 0:
            raise ValueError("prediction must be a non-empty position x horizon matrix")
        if not np.isfinite(array).all():
            raise ValueError("prediction contains NaN or Inf")
        return self

    def array(self) -> np.ndarray:
        return np.asarray(self.values, dtype=float)

    @property
    def shape(self) -> tuple[int, int]:
        array = self.array()
        return int(array.shape[0]), int(array.shape[1])


class ArtifactEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    size_bytes_at_save: int = Field(gt=0)
    size_bytes_at_load: int = Field(gt=0)
    sha256_at_save: str
    sha256_at_load: str

    @field_validator("sha256_at_save", "sha256_at_load")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("SHA-256 must be 64 lowercase hexadecimal characters")
        return value


class ModelSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1)
    family: Literal["local", "regression", "torch", "foundation", "ensemble", "conformal"]
    public_name: str = Field(min_length=1)
    class_path: str = Field(min_length=1)
    parameters_sha256: str
    fitted: bool
    training_state_present: bool
    covariate_state_present: bool

    @field_validator("parameters_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("parameters_sha256 must be a SHA-256 digest")
        return value


class PersistenceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1)
    family: Literal["local", "regression", "torch", "foundation", "ensemble", "conformal"]
    public_name: str = Field(min_length=1)
    torch_backed: bool = False
    supports_clean: bool = False
    supports_checkpoint: bool = False
    supports_weights: bool = False
    requested_accelerator: Literal["cpu", "gpu", "not_applicable"] = "not_applicable"
    device_index: int | None = Field(default=None, ge=0)
    methods: tuple[PersistenceMethod, ...] = ("manual",)
    prediction_atol: float = Field(default=1e-12, ge=0.0)
    prediction_rtol: float = Field(default=1e-9, ge=0.0)

    @model_validator(mode="after")
    def validate_spec(self) -> PersistenceSpec:
        if not self.methods or len(set(self.methods)) != len(self.methods):
            raise ValueError("methods must be non-empty and unique")
        if "manual" not in self.methods:
            raise ValueError("every family requires manual save/load certification")
        if self.torch_backed:
            if self.requested_accelerator == "not_applicable":
                raise ValueError("torch-backed models require an accelerator request")
            if self.requested_accelerator == "gpu" and self.device_index is None:
                raise ValueError("GPU-backed models require device_index")
        elif self.requested_accelerator != "not_applicable" or self.device_index is not None:
            raise ValueError("non-torch models must use not_applicable device status")
        if "manual_clean" in self.methods and not self.supports_clean:
            raise ValueError("manual_clean requires supports_clean")
        if any(method.startswith("checkpoint_") for method in self.methods):
            if not self.supports_checkpoint or not self.torch_backed:
                raise ValueError("checkpoint methods require torch-backed checkpoint support")
        if "weights" in self.methods and (not self.supports_weights or not self.torch_backed):
            raise ValueError("weights method requires torch-backed weights support")
        cross = {"cross_device_cpu", "cross_device_cuda"} & set(self.methods)
        if cross and not self.torch_backed:
            raise ValueError("cross-device methods require a torch-backed model")
        return self


class PersistenceCampaignConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    run_id: str = Field(min_length=1)
    specs: tuple[PersistenceSpec, ...]
    outer_workers: int = Field(default=8, ge=1, le=64)
    max_gpu_jobs: int = Field(default=1, ge=1, le=8)

    @model_validator(mode="after")
    def validate_campaign(self) -> PersistenceCampaignConfig:
        families = tuple(spec.family for spec in self.specs)
        if set(families) != set(P11_FAMILIES) or len(families) != len(P11_FAMILIES):
            raise ValueError("P11 requires exactly one spec for each persistence family")
        if len({spec.model_id for spec in self.specs}) != len(self.specs):
            raise ValueError("model_id values must be unique")
        if self.outer_workers != 8:
            raise ValueError("P11 outer worker contract is fixed at eight")
        if self.max_gpu_jobs != 1:
            raise ValueError("P11 serializes GPU persistence jobs")
        return self


class PersistenceTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str
    family: str
    public_name: str
    method: PersistenceMethod


class PersistenceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task: PersistenceTask
    save_process_pid: int = Field(ge=1)
    load_process_pid: int = Field(ge=1)
    save_process_ended: bool
    loaded_from_disk: bool
    object_identity_reused: bool = False
    artifacts: tuple[ArtifactEvidence, ...]
    before_snapshot: ModelSnapshot
    after_snapshot: ModelSnapshot
    prediction_before: TemporalPrediction
    prediction_after: TemporalPrediction
    clean_requested: bool = False
    requested_map_location: str | None = None
    checkpoint_kind: Literal["best", "last"] | None = None
    trainer_state_restored: bool | None = None
    optimizer_state_restored: bool | None = None
    scheduler_state_restored: bool | None = None
    model_initialized_before_weights: bool | None = None
    weights_loaded: bool | None = None
    encoders_loaded: bool | None = None
    device_before: TorchRuntimeObservation | None = None
    device_after: TorchRuntimeObservation | None = None
    argument_ledger: tuple[dict[str, Any], ...] = ()


class ArgumentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target: str
    argument: str
    status: Literal["accepted", "rejected"]
    reason: str
    value_repr: str


def classify_arguments(
    target: Callable[..., Any],
    requested: Mapping[str, Any],
    *,
    target_name: str,
) -> tuple[dict[str, Any], tuple[ArgumentDecision, ...]]:
    signature = inspect.signature(target)
    accepted_names = set(signature.parameters)
    accepts_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    effective: dict[str, Any] = {}
    ledger: list[ArgumentDecision] = []
    rejected: list[str] = []
    for key, value in requested.items():
        accepted = key in accepted_names or accepts_kwargs
        if accepted:
            effective[key] = value
        else:
            rejected.append(key)
        ledger.append(
            ArgumentDecision(
                target=target_name,
                argument=key,
                status="accepted" if accepted else "rejected",
                reason=(
                    "callable signature accepts argument"
                    if accepted
                    else "argument absent from callable signature"
                ),
                value_repr=repr(value),
            )
        )
    if rejected:
        raise PersistenceContractError(
            f"rejected persistence arguments for {target_name}: {sorted(rejected)}"
        )
    return effective, tuple(ledger)


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def manifest_sha256(artifacts: tuple[ArtifactEvidence, ...]) -> str:
    return canonical_sha256(
        [
            artifact.model_dump(mode="json")
            for artifact in sorted(artifacts, key=lambda item: item.path)
        ]
    )

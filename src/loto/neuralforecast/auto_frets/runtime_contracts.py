"""Strict target-host runtime contracts for AutoFreTS certification."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .contracts import ArchitectureProfile, TrainingProfile, resolve_architecture

RUNTIME_REQUEST_SCHEMA_VERSION = "1.0.0"
RUNTIME_RESPONSE_SCHEMA_VERSION = "1.0.0"
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_REVISION_PATTERN = r"^[0-9a-f]{40}$"


class StrictRuntimeModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
    )


class AutoFreTSRuntimeRequest(StrictRuntimeModel):
    """Immutable request for one fixed AutoFreTS runtime lane."""

    schema_version: Literal["1.0.0"] = RUNTIME_REQUEST_SCHEMA_VERSION
    run_id: str
    profile: Literal["CPU_SMOKE", "GPU_FORMAL"]
    execution_mode: Literal["direct", "ray", "optuna"] = "direct"
    requested_device: Literal["cpu", "cuda"]
    expected_neuralforecast_version: Literal["3.2.0"] = "3.2.0"
    source_revision: str = Field(pattern=_REVISION_PATTERN)
    source_tree_sha256: str = Field(pattern=_SHA256_PATTERN)
    horizon: int = Field(default=1, ge=1, le=16)
    architecture_profile: ArchitectureProfile = ArchitectureProfile.COMPACT
    training_profile: TrainingProfile = TrainingProfile.SMOKE
    learning_rate: float = Field(default=1e-3, gt=0.0, lt=1.0)
    batch_size: int = Field(default=4, ge=1, le=128)
    windows_batch_size: int = Field(default=8, ge=1, le=4096)
    scaler_type: Literal["identity", "robust"] = "identity"
    seed: int = Field(default=1, ge=1, le=2_147_483_647)
    history_length: int = Field(default=96, ge=16, le=100_000)
    validation_size: int = Field(default=1, ge=1, le=1_000)
    precision: Literal["32-true"] = "32-true"
    replay_tolerance: float = Field(default=0.0, ge=0.0, le=1.0)
    timeout_seconds: float = Field(default=3_600.0, gt=0.0, le=86_400.0)
    working_directory: str

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        if not _RUN_ID_PATTERN.fullmatch(value):
            raise ValueError("run_id must be a portable non-empty identifier")
        return value

    @field_validator("working_directory")
    @classmethod
    def validate_working_directory(cls, value: str) -> str:
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("working_directory must be absolute")
        if "\x00" in value:
            raise ValueError("working_directory contains a NUL character")
        return value

    @model_validator(mode="after")
    def validate_runtime_policy(self) -> AutoFreTSRuntimeRequest:
        if self.profile == "CPU_SMOKE" and self.requested_device != "cpu":
            raise ValueError("CPU_SMOKE requires requested_device=cpu")
        if self.profile == "GPU_FORMAL" and self.requested_device != "cuda":
            raise ValueError("GPU_FORMAL requires requested_device=cuda")
        architecture = resolve_architecture(self.horizon, self.architecture_profile)
        minimum_history = architecture.input_size + self.horizon + self.validation_size + 1
        if self.history_length < minimum_history:
            raise ValueError(
                f"history_length must be at least {minimum_history} "
                "for the selected geometry"
            )
        return self


class SourceFileRecord(StrictRuntimeModel):
    relative_path: str = Field(min_length=1, max_length=4096)
    sha256: str = Field(pattern=_SHA256_PATTERN)
    size_bytes: int = Field(ge=0)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or "\\" in value or ":" in value:
            raise ValueError("source path must be canonical and relative")
        if any(part in {"", ".", ".."} for part in value.split("/")):
            raise ValueError("source path contains an unsafe component")
        return value


class GPUProcessSampleRecord(StrictRuntimeModel):
    provider_pid: int = Field(ge=1)
    gpu_uuid: str = Field(min_length=1, max_length=256)
    used_memory_bytes: int = Field(gt=0)
    observed_at_utc: datetime

    @field_validator("observed_at_utc")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("GPU sample timestamp must be timezone-aware")
        return value


class AutoFreTSWorkerResponse(StrictRuntimeModel):
    """One isolated provider-process observation."""

    schema_version: Literal["1.0.0"] = RUNTIME_RESPONSE_SCHEMA_VERSION
    status: Literal["PASS", "FAILED"]
    run_label: Literal["run-a", "run-b"]
    execution_mode: Literal["direct", "ray", "optuna"]
    provider_pid: int = Field(ge=1)
    package_version: str | None = None
    source_revision: str | None = Field(default=None, pattern=_REVISION_PATTERN)
    source_tree_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    requested_device: Literal["cpu", "cuda"]
    effective_device: Literal["cpu", "cuda"] | None = None
    cpu_fallback: bool | None = None
    provider_gpu_pid: int | None = Field(default=None, ge=1)
    gpu_uuid: str | None = Field(default=None, min_length=1, max_length=256)
    peak_vram_bytes: int | None = Field(default=None, ge=0)
    external_gpu_samples: tuple[GPUProcessSampleRecord, ...] = ()
    output: tuple[tuple[float, ...], ...] | None = None
    pre_reload_output: tuple[tuple[float, ...], ...] | None = None
    source_verified: bool = False
    package_verified: bool = False
    load_success: bool = False
    input_validation_success: bool = False
    fit_success: bool = False
    inference_success: bool = False
    save_succeeded: bool = False
    reload_succeeded: bool = False
    re_predict_succeeded: bool = False
    auto_backend_executed: bool = False
    maximum_reload_difference: float | None = Field(default=None, ge=0.0)
    bundle_path: str | None = None
    fitted_model_class: str | None = None
    fft_dtype: Literal["float32"] | None = None
    temporal_fft_bins: int | None = Field(default=None, gt=0)
    channel_frequency_mixing: bool | None = None
    parameter_count: int | None = Field(default=None, gt=0)
    expected_parameter_count: int | None = Field(default=None, gt=0)
    error_type: str | None = None
    error_message: str | None = None

    @field_validator("output", "pre_reload_output")
    @classmethod
    def validate_numeric_output(
        cls,
        value: tuple[tuple[float, ...], ...] | None,
    ) -> tuple[tuple[float, ...], ...] | None:
        if value is None:
            return value
        if not value or any(not row for row in value):
            raise ValueError("runtime output must be a non-empty rectangular matrix")
        width = len(value[0])
        if any(len(row) != width for row in value):
            raise ValueError("runtime output must not be ragged")
        if any(not math.isfinite(item) for row in value for item in row):
            raise ValueError("runtime output must contain finite values only")
        return value

    @model_validator(mode="after")
    def validate_status(self) -> AutoFreTSWorkerResponse:
        if self.status == "FAILED":
            if not self.error_type or not self.error_message:
                raise ValueError("FAILED response requires error_type and error_message")
            return self
        required = {
            "package_version": self.package_version,
            "source_revision": self.source_revision,
            "source_tree_sha256": self.source_tree_sha256,
            "effective_device": self.effective_device,
            "cpu_fallback": self.cpu_fallback,
            "peak_vram_bytes": self.peak_vram_bytes,
            "output": self.output,
            "pre_reload_output": self.pre_reload_output,
            "maximum_reload_difference": self.maximum_reload_difference,
            "bundle_path": self.bundle_path,
            "fitted_model_class": self.fitted_model_class,
            "fft_dtype": self.fft_dtype,
            "temporal_fft_bins": self.temporal_fft_bins,
            "channel_frequency_mixing": self.channel_frequency_mixing,
            "parameter_count": self.parameter_count,
            "expected_parameter_count": self.expected_parameter_count,
        }
        missing = sorted(key for key, value in required.items() if value is None)
        if missing:
            raise ValueError(f"PASS response is missing fields: {missing}")
        lifecycle = (
            self.source_verified,
            self.package_verified,
            self.load_success,
            self.input_validation_success,
            self.fit_success,
            self.inference_success,
            self.save_succeeded,
            self.reload_succeeded,
            self.re_predict_succeeded,
        )
        if not all(lifecycle):
            raise ValueError("PASS response requires every lifecycle phase to succeed")
        if self.execution_mode == "direct" and self.auto_backend_executed:
            raise ValueError("direct mode cannot claim an Auto backend execution")
        if self.execution_mode != "direct" and not self.auto_backend_executed:
            raise ValueError("Auto execution mode requires backend execution evidence")
        if self.effective_device != self.requested_device:
            raise ValueError("PASS response requested and effective devices differ")
        if self.cpu_fallback:
            raise ValueError("PASS response cannot report CPU fallback")
        if self.fft_dtype != "float32":
            raise ValueError("FreTS PASS response requires float32 FFT evidence")
        if self.channel_frequency_mixing:
            raise ValueError("FreTS position-univariate lane forbids channel mixing")
        if self.parameter_count != self.expected_parameter_count:
            raise ValueError("FreTS parameter count does not match the contract")
        if self.requested_device == "cpu":
            if self.provider_gpu_pid is not None or self.gpu_uuid is not None:
                raise ValueError("CPU response must not report a GPU identity")
            if self.peak_vram_bytes != 0 or self.external_gpu_samples:
                raise ValueError("CPU response must not report GPU memory evidence")
        else:
            if self.provider_gpu_pid != self.provider_pid:
                raise ValueError("CUDA provider_gpu_pid must equal provider_pid")
            if self.gpu_uuid is None or not self.external_gpu_samples:
                raise ValueError("CUDA response requires UUID and external process evidence")
            if self.peak_vram_bytes is None or self.peak_vram_bytes <= 0:
                raise ValueError("CUDA response requires positive peak VRAM")
        return self


def canonical_request_payload(request: AutoFreTSRuntimeRequest) -> dict[str, Any]:
    return request.model_dump(mode="json")


def canonical_request_sha256(request: AutoFreTSRuntimeRequest) -> str:
    encoded = json.dumps(
        canonical_request_payload(request),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_runtime_request(path: Path) -> AutoFreTSRuntimeRequest:
    return AutoFreTSRuntimeRequest.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_worker_response(path: Path) -> AutoFreTSWorkerResponse:
    return AutoFreTSWorkerResponse.model_validate_json(
        path.read_text(encoding="utf-8")
    )


__all__ = [
    "AutoFreTSRuntimeRequest",
    "AutoFreTSWorkerResponse",
    "GPUProcessSampleRecord",
    "RUNTIME_REQUEST_SCHEMA_VERSION",
    "RUNTIME_RESPONSE_SCHEMA_VERSION",
    "SourceFileRecord",
    "canonical_request_payload",
    "canonical_request_sha256",
    "load_runtime_request",
    "load_worker_response",
]

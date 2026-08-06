"""Strict target-host runtime contracts for AutoTimeLLM certification."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .contracts import ArchitectureProfile, PinnedLLMIdentity, resolve_architecture

RUNTIME_REQUEST_SCHEMA_VERSION = "1.0.0"
RUNTIME_RESPONSE_SCHEMA_VERSION = "1.0.0"
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class StrictRuntimeModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
    )


class AutoTimeLLMRuntimeRequest(StrictRuntimeModel):
    """Immutable request for one direct fixed-configuration runtime campaign."""

    schema_version: Literal["1.0.0"] = RUNTIME_REQUEST_SCHEMA_VERSION
    run_id: str
    llm_identity: PinnedLLMIdentity
    profile: Literal["CPU_SMOKE", "GPU_FORMAL"]
    requested_device: Literal["cpu", "cuda"]
    expected_neuralforecast_version: Literal["3.2.0"] = "3.2.0"
    horizon: int = Field(default=1, ge=1, le=16)
    architecture_profile: ArchitectureProfile = ArchitectureProfile.COMPACT
    seed: int = Field(default=1, ge=1, le=2_147_483_647)
    max_steps: int = Field(default=2, ge=1, le=500)
    val_check_steps: int = Field(default=1, ge=1, le=500)
    batch_size: int = Field(default=4, ge=1, le=128)
    windows_batch_size: int = Field(default=8, ge=1, le=4096)
    history_length: int = Field(default=96, ge=16, le=100_000)
    validation_size: int = Field(default=1, ge=1, le=1_000)
    precision: Literal["32-true", "16-mixed", "bf16-mixed"] = "32-true"
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
    def validate_runtime_policy(self) -> AutoTimeLLMRuntimeRequest:
        if self.profile == "CPU_SMOKE" and self.requested_device != "cpu":
            raise ValueError("CPU_SMOKE requires requested_device=cpu")
        if self.profile == "GPU_FORMAL" and self.requested_device != "cuda":
            raise ValueError("GPU_FORMAL requires requested_device=cuda")
        if self.requested_device == "cpu" and self.precision != "32-true":
            raise ValueError("CPU runtime requires precision=32-true")
        if self.val_check_steps > self.max_steps:
            raise ValueError("val_check_steps must not exceed max_steps")
        architecture = resolve_architecture(self.horizon, self.architecture_profile)
        minimum_history = architecture.input_size + self.horizon + self.validation_size + 1
        if self.history_length < minimum_history:
            raise ValueError(
                f"history_length must be at least {minimum_history} for the selected geometry"
            )
        return self


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


class AutoTimeLLMWorkerResponse(StrictRuntimeModel):
    """One provider-process observation written by the runtime worker."""

    schema_version: Literal["1.0.0"] = RUNTIME_RESPONSE_SCHEMA_VERSION
    status: Literal["PASS", "FAILED"]
    run_label: Literal["run-a", "run-b"]
    provider_pid: int = Field(ge=1)
    package_version: str | None = None
    requested_device: Literal["cpu", "cuda"]
    effective_device: Literal["cpu", "cuda"] | None = None
    cpu_fallback: bool | None = None
    provider_gpu_pid: int | None = Field(default=None, ge=1)
    gpu_uuid: str | None = Field(default=None, min_length=1, max_length=256)
    peak_vram_bytes: int | None = Field(default=None, ge=0)
    external_gpu_samples: tuple[GPUProcessSampleRecord, ...] = ()
    output: tuple[tuple[float, ...], ...] | None = None
    pre_reload_output: tuple[tuple[float, ...], ...] | None = None
    load_success: bool = False
    input_validation_success: bool = False
    inference_success: bool = False
    save_succeeded: bool = False
    reload_succeeded: bool = False
    re_predict_succeeded: bool = False
    maximum_reload_difference: float | None = Field(default=None, ge=0.0)
    bundle_path: str | None = None
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
    def validate_status(self) -> AutoTimeLLMWorkerResponse:
        if self.status == "FAILED":
            if not self.error_type or not self.error_message:
                raise ValueError("FAILED response requires error_type and error_message")
            return self
        required = {
            "package_version": self.package_version,
            "effective_device": self.effective_device,
            "cpu_fallback": self.cpu_fallback,
            "peak_vram_bytes": self.peak_vram_bytes,
            "output": self.output,
            "pre_reload_output": self.pre_reload_output,
            "maximum_reload_difference": self.maximum_reload_difference,
            "bundle_path": self.bundle_path,
        }
        missing = sorted(key for key, value in required.items() if value is None)
        if missing:
            raise ValueError(f"PASS response is missing fields: {missing}")
        if not all(
            (
                self.load_success,
                self.input_validation_success,
                self.inference_success,
                self.save_succeeded,
                self.reload_succeeded,
                self.re_predict_succeeded,
            )
        ):
            raise ValueError("PASS response requires every lifecycle phase to succeed")
        if self.effective_device != self.requested_device:
            raise ValueError("PASS response requested and effective devices differ")
        if self.cpu_fallback:
            raise ValueError("PASS response cannot report CPU fallback")
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


def canonical_request_payload(request: AutoTimeLLMRuntimeRequest) -> dict[str, Any]:
    return request.model_dump(mode="json")


def canonical_request_sha256(request: AutoTimeLLMRuntimeRequest) -> str:
    encoded = json.dumps(
        canonical_request_payload(request),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_runtime_request(path: Path) -> AutoTimeLLMRuntimeRequest:
    return AutoTimeLLMRuntimeRequest.model_validate_json(path.read_text(encoding="utf-8"))


def load_worker_response(path: Path) -> AutoTimeLLMWorkerResponse:
    return AutoTimeLLMWorkerResponse.model_validate_json(path.read_text(encoding="utf-8"))


__all__ = [
    "AutoTimeLLMRuntimeRequest",
    "AutoTimeLLMWorkerResponse",
    "GPUProcessSampleRecord",
    "RUNTIME_REQUEST_SCHEMA_VERSION",
    "RUNTIME_RESPONSE_SCHEMA_VERSION",
    "canonical_request_payload",
    "canonical_request_sha256",
    "load_runtime_request",
    "load_worker_response",
]

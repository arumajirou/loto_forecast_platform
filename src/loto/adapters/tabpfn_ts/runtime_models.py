from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .hash_gate import CheckpointEvidence


class RuntimeCertificationError(RuntimeError):
    """Raised when formal runtime evidence does not satisfy the certification contract."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GPUProcessSample(StrictModel):
    pid: int = Field(ge=1)
    gpu_uuid: str = Field(min_length=1)
    used_memory_bytes: int = Field(gt=0)
    observed_at_utc: str = Field(min_length=1)


class ProviderRunEvidence(StrictModel):
    run_index: int = Field(ge=1)
    process_pid: int = Field(ge=1)
    exit_code: int
    started_at_utc: str
    finished_at_utc: str
    request_path: str
    response_path: str
    stdout_path: str
    stderr_path: str
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    predictions: list[float]
    prediction_shape: list[int]
    requested_device: Literal["cpu", "cuda"]
    execution_device: Literal["cpu", "cuda"]
    cpu_fallback: bool
    provider_gpu_pid: int | None
    provider_peak_vram_bytes: int = Field(ge=0)
    parameter_devices: list[str]
    external_gpu_samples: list[GPUProcessSample]
    pid_released_after_exit: bool

    @field_validator("predictions")
    @classmethod
    def validate_predictions(cls, values: list[float]) -> list[float]:
        if len(values) != 37:
            raise ValueError("formal V2 candidate prediction must contain 37 values")
        if not all(math.isfinite(value) for value in values):
            raise ValueError("formal V2 candidate prediction contains non-finite values")
        return values


class RuntimeCertificationReport(StrictModel):
    schema_version: Literal[1] = 1
    run_id: str = Field(min_length=1)
    status: Literal["PASS", "FAIL"]
    certification_class: Literal["GPU_FORMAL", "CPU_SMOKE"]
    created_at_utc: str
    checkpoint_evidence: CheckpointEvidence
    process_runs: list[ProviderRunEvidence]
    separate_process_reload: bool
    deterministic_replay: bool
    max_absolute_prediction_difference: float = Field(ge=0.0)
    prediction_locked_before_actuals: bool
    failure_reason: str | None = None

    @model_validator(mode="after")
    def validate_pass(self) -> RuntimeCertificationReport:
        if self.status == "PASS":
            if len(self.process_runs) < 2:
                raise ValueError("formal runtime certification requires at least two processes")
            if not self.separate_process_reload or not self.deterministic_replay:
                raise ValueError("PASS requires separate-process deterministic replay")
            if not self.prediction_locked_before_actuals:
                raise ValueError("PASS requires prediction locking before actuals")
            if self.failure_reason is not None:
                raise ValueError("PASS report must not contain failure_reason")
        return self


class RuntimeCertificationConfig(StrictModel):
    run_id: str = Field(min_length=1)
    repo_root: Path
    provider_python: Path
    provider_script: Path
    request_path: Path
    snapshot_path: Path
    repository_cache_root: Path
    output_root: Path
    device: Literal["cpu", "cuda"] = "cuda"
    seed: int = 1
    repeats: int = Field(default=2, ge=2, le=5)
    hold_seconds: float = Field(default=3.0, ge=0.5, le=60.0)
    poll_interval_seconds: float = Field(default=0.1, ge=0.02, le=2.0)
    process_timeout_seconds: float = Field(default=900.0, ge=10.0, le=7200.0)
    prediction_tolerance: float = Field(default=0.0, ge=0.0)
    nvidia_smi_command: str = Field(default="nvidia-smi", min_length=1)
    license_accepted: Literal[True] = True


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_prediction_sha256(predictions: Sequence[float]) -> str:
    payload = json.dumps(list(predictions), separators=(",", ":"), allow_nan=False).encode()
    return sha256_bytes(payload)


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeCertificationError(f"expected JSON object: {path}")
    return payload


def build_sha256_inventory(root: Path, paths: Sequence[Path]) -> str:
    lines = [f"{sha256_path(path)}  {path.relative_to(root)}" for path in sorted(paths)]
    return "\n".join(lines) + "\n"

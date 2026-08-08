from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EXPECTED_BASICTS_VERSION = "1.1.0"
EXPECTED_UPSTREAM_REVISION = "c2bb6e31e591167e84459775a21a62e70a5893ce"
SCHEMA_VERSION = "loto-basicts-provider-v1"


class BasicTSOperation(StrEnum):
    IDENTITY = "identity"
    VALIDATE_CONFIG = "validate_config"
    COMPILE_DATASET = "compile_dataset"
    CONSTRUCT_FORWARD_SAVE_LOAD_SMOKE = "construct_forward_save_load_smoke"


class BasicTSStatus(StrEnum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"
    EXECUTION_PENDING = "EXECUTION_PENDING"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ImportReference(StrictModel):
    module: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=100)

    @field_validator("module")
    @classmethod
    def validate_module(cls, value: str) -> str:
        parts = value.split(".")
        if any(not part.isidentifier() or part.startswith("_") for part in parts):
            raise ValueError("module must contain public Python identifiers only")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.isidentifier() or value.startswith("_"):
            raise ValueError("name must be a public Python identifier")
        return value


class SafeConfig(StrictModel):
    model: ImportReference = Field(
        default_factory=lambda: ImportReference(
            module="loto.adapters.basicts.smoke_model",
            name="TinyLinearForecaster",
        )
    )
    optimizer: ImportReference = Field(
        default_factory=lambda: ImportReference(module="torch.optim", name="Adam")
    )
    lr_scheduler: ImportReference | None = None
    input_len: Annotated[int, Field(ge=2, le=4096)] = 8
    output_len: Annotated[int, Field(ge=1, le=512)] = 1
    channels: Annotated[int, Field(ge=1, le=64)] = 3
    seed: Annotated[int, Field(ge=0, le=2**31 - 1)] = 1
    gpus: None = None
    eval_after_train: Literal[False] = False
    test_interval: None = None
    deterministic: Literal[True] = True


class DatasetRow(StrictModel):
    draw_no: Annotated[int, Field(gt=0)]
    values: list[int] = Field(min_length=1, max_length=64)


class DatasetPayload(StrictModel):
    game: Literal["numbers3", "numbers4", "miniloto", "loto6", "loto7"]
    rows: list[DatasetRow] = Field(min_length=5)
    validation_size: Annotated[int, Field(ge=1)] = 1
    holdout_size: Annotated[int, Field(ge=1)] = 1

    @model_validator(mode="after")
    def validate_split_capacity(self) -> DatasetPayload:
        if self.validation_size + self.holdout_size >= len(self.rows) - 1:
            raise ValueError("dataset must retain at least two training rows")
        return self


class BasicTSProviderRequest(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    request_id: str = Field(min_length=1, max_length=100)
    operation: BasicTSOperation
    artifact_dir: str = Field(min_length=1, max_length=1000)
    config: SafeConfig | None = None
    dataset: DatasetPayload | None = None

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str) -> str:
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
        if not set(value) <= allowed or value in {".", ".."}:
            raise ValueError("request_id contains unsafe characters")
        return value

    @field_validator("artifact_dir")
    @classmethod
    def validate_artifact_dir(cls, value: str) -> str:
        path = PurePosixPath(value.replace("\\", "/"))
        if ".." in path.parts:
            raise ValueError("artifact_dir must not contain parent traversal")
        return value

    @model_validator(mode="after")
    def validate_operation_payload(self) -> BasicTSProviderRequest:
        if (
            self.operation
            in {
                BasicTSOperation.VALIDATE_CONFIG,
                BasicTSOperation.CONSTRUCT_FORWARD_SAVE_LOAD_SMOKE,
            }
            and self.config is None
        ):
            raise ValueError(f"config is required for {self.operation}")
        if self.operation == BasicTSOperation.COMPILE_DATASET and self.dataset is None:
            raise ValueError("dataset is required for compile_dataset")
        return self


class ErrorEvidence(StrictModel):
    phase: str
    exception_type: str
    message: str
    traceback: str


class BasicTSProviderResponse(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    request_id: str
    operation: BasicTSOperation
    status: BasicTSStatus
    actual_execution: bool
    package_version: str | None = None
    upstream_revision: str = EXPECTED_UPSTREAM_REVISION
    cpu_only: Literal[True] = True
    cpu_fallback: Literal[False] = False
    evidence: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    error: ErrorEvidence | None = None

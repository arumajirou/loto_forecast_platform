from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CampaignStage(StrEnum):
    INVENTORY = "inventory"
    PLAN = "plan"
    SMOKE = "smoke"
    COVERAGE = "coverage"
    API_COVERAGE = "api-coverage"
    HPO = "hpo"
    VALIDATE_TRIALS = "validate-trials"
    OOF = "oof"
    HOLDOUT = "holdout"
    PROSPECTIVE = "prospective"
    VERIFY = "verify"


class CoverageStatus(StrEnum):
    EXECUTED = "EXECUTED"
    EXECUTED_ALTERNATE = "EXECUTED_ALTERNATE"
    FIXED_BY_DATA_CONTRACT = "FIXED_BY_DATA_CONTRACT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNSUPPORTED_BY_VERSION = "UNSUPPORTED_BY_VERSION"
    FAILED = "FAILED"
    PLANNED = "PLANNED"


class SplitConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validation_draws: int = 50
    holdout_draws: int = 20
    oof_folds: int = 5
    oof_validation_draws: int = 10
    oof_origins_per_fold: int = 3

    @field_validator(
        "validation_draws",
        "holdout_draws",
        "oof_folds",
        "oof_validation_draws",
        "oof_origins_per_fold",
    )
    @classmethod
    def positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("split sizes must be >= 1")
        return value


class SearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["ray", "optuna"] = "ray"
    strategy: Literal["auto", "random", "tpe", "cmaes"] = "auto"
    num_samples: int = 10
    search_seed: int = 1
    time_budget: int | None = None
    refit_with_val: bool = False
    verbose: bool = False
    allow_fallback: bool = False
    optuna_smoke: bool = True
    coverage_random_samples: int = 4

    @field_validator("num_samples", "coverage_random_samples")
    @classmethod
    def positive_samples(cls, value: int) -> int:
        if value < 1:
            raise ValueError("sample counts must be >= 1")
        return value


class ResourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logical_workers: int = 8
    cpus_per_trial: float = 4.0
    gpus_per_trial: float = 0.25
    gpu_concurrency: int = 4
    accelerator: Literal["gpu", "cpu", "auto"] = "gpu"
    devices: int = 1
    precision: str = "32-true"
    max_retries: int = 2
    parallel_fixed_tasks: bool = True

    @field_validator("logical_workers", "gpu_concurrency", "devices")
    @classmethod
    def positive_int(cls, value: int) -> int:
        if value < 1:
            raise ValueError("resource counts must be >= 1")
        return value

    @field_validator("cpus_per_trial", "gpus_per_trial")
    @classmethod
    def nonnegative_float(cls, value: float) -> float:
        if value < 0:
            raise ValueError("resource values must be >= 0")
        return value


class PersistenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persist_all_successful_trials: bool = True
    require_trial_checkpoint: bool = True
    verify_load_predict: bool = True
    atomic_write: bool = True
    save_dataset: bool = True
    freeze_prospective: bool = True


class CampaignConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id_prefix: str = "miniloto-all-auto"
    data_path: Path
    output_root: Path = Path("artifacts/miniloto-all-auto")
    h: int = 1
    freq: int | str = 1
    number_columns: list[str] = Field(default_factory=lambda: ["P1", "P2", "P3", "P4", "P5"])
    draw_id_candidates: list[str] = Field(
        default_factory=lambda: ["draw_id", "draw", "回号", "開催回", "id"]
    )
    draw_index_candidates: list[str] = Field(
        default_factory=lambda: ["draw_index", "index", "回号", "開催回"]
    )
    model_seeds: list[int] = Field(default_factory=lambda: [1, 42, 2026])
    local_scaler_type: str | None = None
    local_static_scaler_type: str | None = None
    split: SplitConfig = Field(default_factory=SplitConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    resources: ResourceConfig = Field(default_factory=ResourceConfig)
    persistence: PersistenceConfig = Field(default_factory=PersistenceConfig)
    include_tracks: list[str] = Field(
        default_factory=lambda: ["u_shared", "u_local", "m_joint", "h_hint"]
    )
    include_models: list[str] | None = None
    exclude_models: list[str] = Field(default_factory=list)
    max_steps_smoke: int = 1
    val_check_steps_smoke: int = 1
    max_tasks: int | None = None
    extra_base_auto_args: dict[str, Any] = Field(default_factory=dict)
    extra_neuralforecast_args: dict[str, Any] = Field(default_factory=dict)
    extra_fit_args: dict[str, Any] = Field(default_factory=dict)

    @field_validator("h", "max_steps_smoke", "val_check_steps_smoke")
    @classmethod
    def positive_value(cls, value: int) -> int:
        if value < 1:
            raise ValueError("value must be >= 1")
        return value

    @field_validator("model_seeds")
    @classmethod
    def seeds_not_empty(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("model_seeds must not be empty")
        if len(set(value)) != len(value):
            raise ValueError("model_seeds must be unique")
        return value

    @model_validator(mode="after")
    def validate_split(self) -> CampaignConfig:
        if self.split.oof_validation_draws > self.split.validation_draws:
            raise ValueError("oof_validation_draws cannot exceed validation_draws")
        return self

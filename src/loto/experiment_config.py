from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    game: str = "loto7"
    input: str
    target_mode: Literal["candidate", "position", "both"] = "both"
    feature_windows: list[int] = Field(default_factory=lambda: [5, 10, 20, 30, 50, 100])
    exponential_halflives: list[float] = Field(default_factory=lambda: [5.0, 10.0, 20.0, 50.0])
    min_train_draws: int = 100

    @field_validator("feature_windows")
    @classmethod
    def windows_positive_unique(cls, value: list[int]) -> list[int]:
        if not value or any(v <= 0 for v in value):
            raise ValueError("feature_windows must contain positive integers")
        return sorted(set(value))


class CVConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outer_folds: int = 5
    inner_folds: int = 3
    test_size: int = 20
    gap: int = 0
    expanding: bool = True
    holdout_size: int = 50
    seeds: list[int] = Field(default_factory=lambda: [42, 1729, 20260730])
    min_train_size: int = 100

    @model_validator(mode="after")
    def validate_sizes(self):
        if min(self.outer_folds, self.inner_folds, self.test_size, self.min_train_size) <= 0:
            raise ValueError("CV sizes/folds must be positive")
        if not self.seeds:
            raise ValueError("at least one seed is required")
        return self


class ObjectiveConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    primary: Literal["mean_hits_at_7", "mean_within_1", "all_positions_within_1"] = "mean_hits_at_7"
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "mean_hits_at_7": 0.45,
            "mean_within_1": 0.30,
            "all_positions_within_1": 0.10,
            "brier": -0.10,
            "ece": -0.05,
        }
    )
    calibration_brier_relative_limit: float = 1.02
    max_single_ensemble_weight: float = 0.60


class SearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backend: Literal["none", "optuna", "ray"] = "none"
    trials: int = 20
    timeout_seconds: int | None = None
    parallel_jobs: int = 1
    cpus_per_trial: float = 1.0
    gpus_per_trial: float = 0.0
    fail_fast: bool = False
    max_consecutive_failures: int = 5
    sampler: Literal["tpe", "random", "cmaes"] = "tpe"
    pruner: Literal["median", "hyperband", "none"] = "median"


class ObservabilityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mlflow_uri: str | None = None
    experiment_name: str = "loto-v2-research"
    jsonl_log: bool = True
    log_level: str = "INFO"
    prometheus_port: int | None = None
    otlp_endpoint: str | None = None
    trace_sample_ratio: float = 1.0
    capture_gpu: bool = True
    capture_process_tree: bool = True
    profile: Literal["none", "py-spy", "torch"] = "none"


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output: str
    device: Literal["auto", "cpu", "cuda"] = "auto"
    precision: Literal["32", "16-mixed", "bf16-mixed"] = "32"
    deterministic: bool = True
    cache_dir: str = ".cache/loto"
    worker_isolation: Literal["inprocess", "subprocess", "container"] = "subprocess"
    model_timeout_seconds: int = 1800
    max_memory_mb: int | None = None
    resume: bool = True


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "2.1.0"
    data: DataConfig
    models: list[str] = Field(
        default_factory=lambda: ["uniform", "frequency", "logistic", "extra-trees"]
    )
    model_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    cv: CVConfig = Field(default_factory=CVConfig)
    objective: ObjectiveConfig = Field(default_factory=ObjectiveConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    runtime: RuntimeConfig

    @field_validator("models")
    @classmethod
    def models_nonempty_unique(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("models must not be empty")
        return list(dict.fromkeys(value))

    @property
    def config_hash(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    @classmethod
    def from_file(cls, path: str | Path) -> ExperimentConfig:
        path = Path(path)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls.model_validate(raw)

    def write_resolved(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return path

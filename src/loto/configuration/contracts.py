"""Strict, dependency-light configuration contracts for new workflows.

This foundation is separate from legacy experiment and model-specific schemas. Existing YAML
files are not migrated or reinterpreted by importing this module.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

CONFIG_SCHEMA_VERSION = "1.0.0"
REDACTED_VALUE = "<redacted>"
MetricName = Literal[
    "Hit@±1",
    "MAE",
    "MSE",
    "RMSE",
    "Position Hit@±1",
    "All-position Hit@±1",
]


class StrictConfigModel(BaseModel):
    """Base model for immutable, strict Pydantic v2 configuration."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
    )


class ProtectedStagePolicy(StrictConfigModel):
    """Fail-closed policy for protected evaluation stages."""

    auto_run: Literal[False] = False
    auto_open_actuals: Literal[False] = False
    explicit_approval_required: Literal[True] = True


class SplitPolicy(StrictConfigModel):
    """Chronological split and Train-only fitting policy."""

    immutable: Literal[True] = True
    chronological: Literal[True] = True
    model_fit_scope: Literal["train_only"] = "train_only"
    scaler_fit_scope: Literal["train_only"] = "train_only"
    encoder_fit_scope: Literal["train_only"] = "train_only"
    feature_selection_scope: Literal["train_only"] = "train_only"
    hyperparameter_tuning_scope: Literal["train_only"] = "train_only"
    holdout: ProtectedStagePolicy = Field(default_factory=ProtectedStagePolicy)
    prospective: ProtectedStagePolicy = Field(default_factory=ProtectedStagePolicy)


class MetricPolicy(StrictConfigModel):
    primary_metric: Literal["Hit@±1"] = "Hit@±1"
    report_metrics: list[MetricName] = Field(
        default_factory=lambda: [
            "Hit@±1",
            "MAE",
            "MSE",
            "RMSE",
            "Position Hit@±1",
            "All-position Hit@±1",
        ],
        min_length=4,
    )

    @field_validator("report_metrics")
    @classmethod
    def require_metrics(cls, value: list[MetricName]) -> list[MetricName]:
        if len(value) != len(set(value)):
            raise ValueError("report_metrics must not contain duplicates")
        required = {"Hit@±1", "MAE", "MSE", "RMSE"}
        missing = sorted(required.difference(value))
        if missing:
            raise ValueError(f"report_metrics missing required metrics: {missing}")
        return value


class SeedPolicy(StrictConfigModel):
    seeds: list[int] = Field(default_factory=lambda: [1], min_length=1)
    aggregation: Literal["mean_variance_worst"] = "mean_variance_worst"
    best_seed_only_selection: Literal[False] = False

    @field_validator("seeds")
    @classmethod
    def validate_seeds(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("seeds must be unique")
        if any(seed < 0 or seed > 2_147_483_647 for seed in value):
            raise ValueError("seeds must be between 0 and 2147483647")
        return value


class EvaluationPolicy(StrictConfigModel):
    metrics: MetricPolicy = Field(default_factory=MetricPolicy)
    seed_policy: SeedPolicy = Field(default_factory=SeedPolicy)


class DevicePolicy(StrictConfigModel):
    requested: Literal["cpu", "cuda"] = "cpu"
    cpu_fallback_policy: Literal[
        "not_applicable",
        "forbid",
        "allow_with_partial_status",
    ] = "not_applicable"

    @model_validator(mode="after")
    def validate_fallback_policy(self) -> DevicePolicy:
        if self.requested == "cpu" and self.cpu_fallback_policy != "not_applicable":
            raise ValueError("CPU requests require cpu_fallback_policy=not_applicable")
        if self.requested == "cuda" and self.cpu_fallback_policy == "not_applicable":
            raise ValueError("CUDA requests require an explicit CPU fallback policy")
        return self


class RuntimePolicy(StrictConfigModel):
    output_dir: str = Field(min_length=1, max_length=4096)
    device: DevicePolicy = Field(default_factory=DevicePolicy)

    @field_validator("output_dir")
    @classmethod
    def output_dir_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("output_dir must not be blank")
        return value


class MLflowPolicy(StrictConfigModel):
    enabled: bool = False
    tracking_uri: str | None = None
    experiment_name: str = Field(default="loto-config-foundation", min_length=1, max_length=256)
    token: SecretStr | None = None

    @model_validator(mode="after")
    def validate_enabled_fields(self) -> MLflowPolicy:
        if self.enabled and not (self.tracking_uri or "").strip():
            raise ValueError("enabled MLflow requires tracking_uri")
        return self


class ObservabilityPolicy(StrictConfigModel):
    mlflow: MLflowPolicy = Field(default_factory=MLflowPolicy)


class GitMetadataPolicy(StrictConfigModel):
    enabled: bool = True
    require_commit: bool = True
    capture_dirty_state: bool = True
    require_clean_worktree: bool = False

    @model_validator(mode="after")
    def validate_git_policy(self) -> GitMetadataPolicy:
        if self.require_clean_worktree and not self.capture_dirty_state:
            raise ValueError("require_clean_worktree requires capture_dirty_state")
        return self


class StrictFoundationConfig(StrictConfigModel):
    """Versioned strict schema for new configuration consumers."""

    config_schema_version: Literal["1.0.0"] = CONFIG_SCHEMA_VERSION
    experiment_name: str = Field(min_length=1, max_length=128)
    runtime: RuntimePolicy
    split_policy: SplitPolicy = Field(default_factory=SplitPolicy)
    evaluation: EvaluationPolicy = Field(default_factory=EvaluationPolicy)
    observability: ObservabilityPolicy = Field(default_factory=ObservabilityPolicy)
    git_metadata: GitMetadataPolicy = Field(default_factory=GitMetadataPolicy)

    @field_validator("experiment_name")
    @classmethod
    def experiment_name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("experiment_name must not be blank")
        return value

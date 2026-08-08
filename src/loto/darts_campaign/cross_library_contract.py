from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROVIDER_TRACKS = (
    "darts_native",
    "darts_neuralforecast_wrapper",
    "darts_statsforecast_wrapper",
    "standalone_neuralforecast",
    "standalone_mlforecast",
    "standalone_statsforecast",
    "autogluon",
    "foundation_direct",
)

REQUIRED_BASELINES = (
    "random",
    "fixed",
    "mean",
    "median",
    "last",
    "frequency",
    "statistical",
)

REQUIRED_METRICS = (
    "hit_at_plus_minus_1",
    "position_hit_at_plus_minus_1",
    "all_position_hit_at_plus_minus_1",
    "mae",
    "mse",
    "rmse",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UNPINNED = {"", "latest", "main", "master", "head", "unresolved", "unknown"}


class CrossLibraryContractError(ValueError):
    """Raised when a cross-library comparison request is not fair or auditable."""


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_sha256(value: str, *, field_name: str) -> str:
    normalized = value.lower()
    if not _SHA256_RE.fullmatch(normalized):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 value")
    return normalized


def validate_pinned_identity(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if normalized.lower() in _UNPINNED:
        raise ValueError(f"{field_name} must be explicitly pinned")
    return normalized


class AlgorithmIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    algorithm_family: Literal[
        "statistical",
        "regression",
        "torch",
        "foundation",
        "ensemble",
        "conformal",
    ]
    base_library: str = Field(min_length=1)
    base_model: str = Field(min_length=1)
    base_revision: str = Field(min_length=1)
    estimator_id: str | None = None
    model_config_sha256: str

    @field_validator("base_library", "base_model")
    @classmethod
    def strip_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("algorithm identity fields must be non-empty")
        return value

    @field_validator("base_revision")
    @classmethod
    def pin_revision(cls, value: str) -> str:
        return validate_pinned_identity(value, field_name="base_revision")

    @field_validator("model_config_sha256")
    @classmethod
    def check_config_hash(cls, value: str) -> str:
        return validate_sha256(value, field_name="model_config_sha256")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "algorithm_family": self.algorithm_family,
            "base_library": self.base_library,
            "base_model": self.base_model,
            "base_revision": self.base_revision,
            "estimator_id": self.estimator_id,
            "model_config_sha256": self.model_config_sha256,
        }

    def canonical_key(self) -> str:
        return canonical_sha256(self.canonical_payload())


class ProviderExecution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str = Field(min_length=1)
    track: Literal[
        "darts_native",
        "darts_neuralforecast_wrapper",
        "darts_statsforecast_wrapper",
        "standalone_neuralforecast",
        "standalone_mlforecast",
        "standalone_statsforecast",
        "autogluon",
        "foundation_direct",
    ]
    execution_library: str = Field(min_length=1)
    execution_version: str = Field(min_length=1)
    wrapper_library: str | None = None
    wrapper_version: str | None = None
    algorithm: AlgorithmIdentity
    canonical_for_algorithm: bool
    runtime: Literal["notorch", "torch", "external"]
    requested_device: Literal["cpu", "gpu"]

    @field_validator("provider_id", "execution_library")
    @classmethod
    def strip_provider_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("provider fields must be non-empty")
        return value

    @field_validator("execution_version")
    @classmethod
    def pin_execution_version(cls, value: str) -> str:
        return validate_pinned_identity(value, field_name="execution_version")

    @model_validator(mode="after")
    def validate_wrapper_identity(self) -> ProviderExecution:
        if self.track.startswith("darts_"):
            if self.execution_library.lower() != "darts":
                raise ValueError("Darts tracks require execution_library=darts")
        if self.track == "darts_neuralforecast_wrapper":
            if self.wrapper_library != "darts":
                raise ValueError("Darts NeuralForecast wrapper must record wrapper_library=darts")
            if self.algorithm.base_library.lower() != "neuralforecast":
                raise ValueError("Darts NeuralForecast wrapper must identify NeuralForecast base")
        if self.track == "darts_statsforecast_wrapper":
            if self.wrapper_library != "darts":
                raise ValueError("Darts StatsForecast wrapper must record wrapper_library=darts")
            if self.algorithm.base_library.lower() != "statsforecast":
                raise ValueError("Darts StatsForecast wrapper must identify StatsForecast base")
        standalone = {
            "standalone_neuralforecast": "neuralforecast",
            "standalone_mlforecast": "mlforecast",
            "standalone_statsforecast": "statsforecast",
        }
        if self.track in standalone:
            expected = standalone[self.track]
            if self.execution_library.lower() != expected:
                raise ValueError(f"{self.track} requires execution_library={expected}")
            if self.wrapper_library is not None:
                raise ValueError("standalone providers must not declare wrapper_library")
        if self.track == "foundation_direct" and self.wrapper_library is not None:
            raise ValueError("foundation_direct must not declare wrapper_library")
        if self.wrapper_library is None and self.wrapper_version is not None:
            raise ValueError("wrapper_version requires wrapper_library")
        if self.wrapper_library is not None and self.wrapper_version is None:
            raise ValueError("wrapper_library requires wrapper_version")
        return self

    def execution_key(self) -> str:
        return canonical_sha256(
            {
                "provider_id": self.provider_id,
                "track": self.track,
                "execution_library": self.execution_library,
                "execution_version": self.execution_version,
                "wrapper_library": self.wrapper_library,
                "wrapper_version": self.wrapper_version,
                "algorithm_key": self.algorithm.canonical_key(),
            }
        )


class TemporalBoundaries(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    train_start: int = Field(default=0, ge=0)
    train_end: int = Field(ge=1)
    validation_start: int = Field(ge=1)
    validation_end: int = Field(ge=2)
    holdout_start: int = Field(ge=2)
    holdout_end: int = Field(ge=3)
    prospective_start: int = Field(ge=3)

    @model_validator(mode="after")
    def validate_time_order(self) -> TemporalBoundaries:
        ordered = (
            self.train_start
            < self.train_end
            <= self.validation_start
            < self.validation_end
            <= self.holdout_start
            < self.holdout_end
            <= self.prospective_start
        )
        if not ordered:
            raise ValueError("Train, Validation, Holdout, and Prospective must be ordered")
        return self


class FairnessContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_data_sha256: str
    comparison_data_sha256: str
    fold_contract_sha256: str
    feature_contract_sha256: str
    code_contract_sha256: str
    boundaries: TemporalBoundaries
    positions: tuple[str, ...]
    target_columns: tuple[str, ...]
    series_layout: Literal[
        "position_local",
        "multivariate",
        "position_global_sequence",
    ]
    horizon: int = Field(ge=1, le=512)
    seeds: tuple[int, ...]
    fold_ids: tuple[int, ...]
    target_lags: tuple[int, ...] = ()
    past_covariate_lags: tuple[int, ...] = ()
    future_covariate_lags: tuple[int, ...] = ()
    past_covariate_columns: tuple[str, ...] = ()
    future_covariate_columns: tuple[str, ...] = ()
    static_covariate_columns: tuple[str, ...] = ()
    scaler_fit_scope: Literal["train"] = "train"
    encoder_fit_scope: Literal["train"] = "train"
    feature_selection_scope: Literal["train"] = "train"
    hpo_scope: Literal["train"] = "train"

    @field_validator(
        "raw_data_sha256",
        "comparison_data_sha256",
        "fold_contract_sha256",
        "feature_contract_sha256",
        "code_contract_sha256",
    )
    @classmethod
    def check_hash(cls, value: str, info: Any) -> str:
        return validate_sha256(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_fairness(self) -> FairnessContract:
        if not self.positions or len(set(self.positions)) != len(self.positions):
            raise ValueError("positions must be non-empty and unique")
        if self.target_columns != self.positions:
            raise ValueError("target_columns must preserve the declared position order")
        if len(self.seeds) < 2 or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("cross-library comparison requires multiple unique seeds")
        if not self.fold_ids or len(set(self.fold_ids)) != len(self.fold_ids):
            raise ValueError("fold_ids must be non-empty and unique")
        if any(lag >= 0 for lag in self.target_lags):
            raise ValueError("target lags must be strictly negative")
        if any(lag >= 0 for lag in self.past_covariate_lags):
            raise ValueError("past covariate lags must be strictly negative")
        covariates = set(self.past_covariate_columns)
        covariates |= set(self.future_covariate_columns)
        covariates |= set(self.static_covariate_columns)
        overlap = sorted(set(self.target_columns) & covariates)
        if overlap:
            raise ValueError(f"target columns cannot be reused as covariates: {overlap}")
        if self.past_covariate_lags and not self.past_covariate_columns:
            raise ValueError("past covariate lags require past covariate columns")
        if self.future_covariate_lags and not self.future_covariate_columns:
            raise ValueError("future covariate lags require future covariate columns")
        return self

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def contract_sha256(self) -> str:
        return canonical_sha256(self.canonical_payload())


class CrossLibraryCampaignConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    run_id: str = Field(min_length=1)
    providers: tuple[ProviderExecution, ...]
    fairness: FairnessContract
    primary_metric: Literal["hit_at_plus_minus_1"] = "hit_at_plus_minus_1"
    metrics: tuple[str, ...] = REQUIRED_METRICS
    baselines: tuple[str, ...] = REQUIRED_BASELINES
    allow_best_seed_only: Literal[False] = False
    require_all_tracks: Literal[True] = True
    require_wrapper_prediction_parity: bool = False
    wrapper_prediction_atol: float = Field(default=1e-12, ge=0.0)
    wrapper_prediction_rtol: float = Field(default=0.0, ge=0.0)
    outer_workers: int = Field(default=8, ge=1, le=64)
    max_gpu_jobs: int = Field(default=1, ge=1, le=8)

    @model_validator(mode="after")
    def validate_campaign(self) -> CrossLibraryCampaignConfig:
        provider_ids = [provider.provider_id for provider in self.providers]
        if not provider_ids or len(provider_ids) != len(set(provider_ids)):
            raise ValueError("provider IDs must be non-empty and unique")
        tracks = {provider.track for provider in self.providers}
        if tracks != set(PROVIDER_TRACKS):
            missing = sorted(set(PROVIDER_TRACKS) - tracks)
            extra = sorted(tracks - set(PROVIDER_TRACKS))
            raise ValueError(f"provider track mismatch: missing={missing}, extra={extra}")
        if set(self.metrics) != set(REQUIRED_METRICS):
            raise ValueError("all required comparison metrics must be retained")
        if set(self.baselines) != set(REQUIRED_BASELINES):
            raise ValueError("all required baseline families must be retained")
        if self.max_gpu_jobs != 1:
            raise ValueError("P12 serializes GPU jobs")
        groups: dict[str, list[ProviderExecution]] = defaultdict(list)
        for provider in self.providers:
            groups[provider.algorithm.canonical_key()].append(provider)
        for algorithm_key, variants in groups.items():
            canonical = [item for item in variants if item.canonical_for_algorithm]
            if len(canonical) != 1:
                raise ValueError(
                    f"each base algorithm requires exactly one canonical execution: {algorithm_key}"
                )
        return self

    def provider_map(self) -> Mapping[str, ProviderExecution]:
        return {provider.provider_id: provider for provider in self.providers}

    def algorithm_groups(self) -> Mapping[str, tuple[ProviderExecution, ...]]:
        grouped: dict[str, list[ProviderExecution]] = defaultdict(list)
        for provider in self.providers:
            grouped[provider.algorithm.canonical_key()].append(provider)
        return {key: tuple(value) for key, value in grouped.items()}

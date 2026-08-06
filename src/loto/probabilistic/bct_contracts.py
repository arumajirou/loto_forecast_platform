from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MODEL_ID = "pp-bayesian-context-tree"
SCHEMA_VERSION = "1.0.0"
SHA256_LENGTH = 64


def _validate_sha256(value: str) -> str:
    if len(value) != SHA256_LENGTH or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("value must be a lowercase 64-character SHA-256 digest")
    return value


def _validate_relative_artifact_path(value: str) -> str:
    if not value or "\\" in value:
        raise ValueError("artifact paths must be non-empty POSIX relative paths")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("artifact paths must not be absolute or contain traversal segments")
    return value


def canonical_payload_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_bct_config(path: str) -> BayesianContextTreeConfigV1:
    with open(path, encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Bayesian Context Tree config must be a YAML mapping")
    return BayesianContextTreeConfigV1.model_validate(payload)


def bct_config_sha256(config: BayesianContextTreeConfigV1) -> str:
    return canonical_payload_sha256(config.model_dump(mode="json"))


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class BayesianContextTreeExactLaneV1(_StrictModel):
    enabled: Literal[True] = True
    exact_posterior: Literal[True] = True
    context_pruning: Literal[False] = False
    posterior_mass_pruning: Literal[False] = False


class BayesianContextTreeBoundedLaneV1(_StrictModel):
    enabled: bool = False
    approximate: Literal[True] = True
    max_nodes_enforced: Literal[True] = True
    pruning_evidence_required: Literal[True] = True


class BayesianContextTreeConfigV1(_StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    model_id: Literal[MODEL_ID] = MODEL_ID
    family: Literal["tree_bayesian"] = "tree_bayesian"
    target_mode: Literal["categorical_context"] = "categorical_context"
    primary_backend: Literal["builtin"] = "builtin"
    native_graph_id: Literal["bayesian_context_tree_v1"] = "bayesian_context_tree_v1"
    implementation_status: Literal["CONTRACT_ONLY"] = "CONTRACT_ONLY"
    active_catalog_registration: Literal[False] = False
    max_depth: int = Field(ge=0, le=128)
    beta: float = Field(gt=0.0, lt=1.0, allow_inf_nan=False)
    prior_concentration: float = Field(gt=0.0, allow_inf_nan=False)
    top_k: int = Field(ge=1, le=10000)
    max_nodes: int = Field(ge=1, le=100_000_000)
    missing_policy: Literal["skip_update_reset_context"] = "skip_update_reset_context"
    update_mode: Literal["predict_before_update"] = "predict_before_update"
    rollout_mode: Literal["horizon1_native_recursive_extension"] = (
        "horizon1_native_recursive_extension"
    )
    exact_lane: BayesianContextTreeExactLaneV1
    bounded_lane: BayesianContextTreeBoundedLaneV1


class BayesianContextTreeChronologyEvidenceV1(_StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    prediction_created_at: datetime
    history_last_index: int = Field(ge=-1)
    prediction_index: int = Field(ge=0)
    actuals_used_through_index: int = Field(ge=-1)
    predict_before_update: Literal[True] = True
    update_after_prediction: Literal[True] = True
    future_actuals_used: Literal[False] = False
    actual_known_at_prediction: Literal[False] = False

    @model_validator(mode="after")
    def validate_chronology(self) -> BayesianContextTreeChronologyEvidenceV1:
        if self.history_last_index >= self.prediction_index:
            raise ValueError("history_last_index must be before prediction_index")
        if self.actuals_used_through_index > self.history_last_index:
            raise ValueError("actuals_used_through_index exceeds the available history")
        return self


class _BayesianContextTreeIdentityV1(_StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    run_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$")
    model_id: Literal[MODEL_ID] = MODEL_ID
    package_version: str = Field(min_length=1, max_length=100)
    source_revision: str = Field(min_length=1, max_length=200)
    model_revision: str = Field(min_length=1, max_length=200)
    config_sha256: str
    weight_sha256: str | None = None
    license: str = Field(min_length=1, max_length=200)
    game: Literal["numbers3", "numbers4", "mini", "loto6", "loto7"]
    target_layout: Literal[
        "per_position_univariate",
        "shared_position_prefixed",
        "joint_token",
    ] = "per_position_univariate"
    alphabet: list[str] = Field(min_length=1)
    alphabet_sha256: str
    context_length: int = Field(ge=0, le=10_000_000)
    prediction_length: int = Field(ge=1, le=10_000)
    max_depth: int = Field(ge=0, le=128)
    beta: float = Field(gt=0.0, lt=1.0, allow_inf_nan=False)
    prior_concentration: float = Field(gt=0.0, allow_inf_nan=False)
    top_k: int = Field(ge=1, le=10000)
    max_nodes: int = Field(ge=1, le=100_000_000)
    seed: int = Field(ge=0, le=2**63 - 1)
    requested_device: Literal["cpu"] = "cpu"
    effective_device: Literal["cpu"] = "cpu"
    cpu_fallback: Literal[False] = False
    actuals_used: list[int] = Field(default_factory=list)
    chronology_evidence: BayesianContextTreeChronologyEvidenceV1

    @field_validator("config_sha256", "alphabet_sha256")
    @classmethod
    def validate_required_sha256(cls, value: str) -> str:
        return _validate_sha256(value)

    @field_validator("weight_sha256")
    @classmethod
    def validate_optional_sha256(cls, value: str | None) -> str | None:
        return None if value is None else _validate_sha256(value)

    @field_validator("alphabet")
    @classmethod
    def validate_alphabet(cls, value: list[str]) -> list[str]:
        if any(not token for token in value):
            raise ValueError("alphabet tokens must not be empty")
        if len(value) != len(set(value)):
            raise ValueError("alphabet tokens must be unique")
        return value

    @field_validator("actuals_used")
    @classmethod
    def validate_actuals_used(cls, value: list[int]) -> list[int]:
        if any(index < 0 for index in value):
            raise ValueError("actuals_used indexes must be non-negative")
        if value != sorted(set(value)):
            raise ValueError("actuals_used indexes must be unique and strictly increasing")
        return value

    @model_validator(mode="after")
    def validate_identity_consistency(self) -> _BayesianContextTreeIdentityV1:
        expected_alphabet_sha = canonical_payload_sha256(self.alphabet)
        if self.alphabet_sha256 != expected_alphabet_sha:
            raise ValueError("alphabet_sha256 does not match the canonical alphabet")
        if self.actuals_used:
            maximum_actual_index = max(self.actuals_used)
            if maximum_actual_index > self.chronology_evidence.actuals_used_through_index:
                raise ValueError("actuals_used contains an index beyond chronology evidence")
            if maximum_actual_index >= self.chronology_evidence.prediction_index:
                raise ValueError("future actual leakage detected")
        return self


class BayesianContextTreeRequestV1(_BayesianContextTreeIdentityV1):
    input_shape: list[int] = Field(min_length=1)
    history: list[str | None]

    @field_validator("input_shape")
    @classmethod
    def validate_input_shape_values(cls, value: list[int]) -> list[int]:
        if any(dimension < 0 for dimension in value):
            raise ValueError("input_shape dimensions must be non-negative")
        return value

    @model_validator(mode="after")
    def validate_request_shape_and_history(self) -> BayesianContextTreeRequestV1:
        if self.input_shape != [len(self.history)]:
            raise ValueError("input_shape must equal the one-dimensional history length")
        if self.context_length != len(self.history):
            raise ValueError("context_length must equal history length")
        illegal = [
            token
            for token in self.history
            if token is not None and token not in self.alphabet
        ]
        if illegal:
            raise ValueError("history contains symbols outside the declared alphabet")
        return self


class BayesianContextTreeResponseV1(_BayesianContextTreeIdentityV1):
    input_shape: list[int] = Field(min_length=1)
    output_shape: list[int] = Field(min_length=2, max_length=2)
    point_forecast: list[str]
    categorical_probabilities: list[list[float]]
    quantiles: dict[str, list[float]] = Field(default_factory=dict)
    samples: list[list[str]] = Field(default_factory=list)
    finite_check: Literal[True]
    categorical_simplex_check: Literal[True]
    suffix_closure_check: Literal[True]
    runtime_pid: int = Field(ge=1)
    gpu_uuid: None = None
    gpu_process_vram_mb: None = None
    state_sha256: str
    prediction_sha256: str
    artifact_paths: list[str] = Field(default_factory=list)

    @field_validator("state_sha256", "prediction_sha256")
    @classmethod
    def validate_response_sha256(cls, value: str) -> str:
        return _validate_sha256(value)

    @field_validator("artifact_paths")
    @classmethod
    def validate_artifact_paths(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("artifact_paths must not contain duplicates")
        return [_validate_relative_artifact_path(path) for path in value]

    @field_validator("quantiles")
    @classmethod
    def validate_categorical_quantiles(
        cls, value: dict[str, list[float]]
    ) -> dict[str, list[float]]:
        if value:
            raise ValueError("quantiles must be empty for a categorical forecast")
        return value

    @model_validator(mode="after")
    def validate_response_outputs(self) -> BayesianContextTreeResponseV1:
        expected_shape = [self.prediction_length, len(self.alphabet)]
        if self.output_shape != expected_shape:
            raise ValueError("output_shape does not match prediction_length and alphabet")
        if self.input_shape != [self.context_length]:
            raise ValueError("input_shape must equal the one-dimensional context length")
        if len(self.point_forecast) != self.prediction_length:
            raise ValueError("point_forecast length does not match prediction_length")
        if any(symbol not in self.alphabet for symbol in self.point_forecast):
            raise ValueError("point_forecast contains a symbol outside the alphabet")
        if len(self.categorical_probabilities) != self.prediction_length:
            raise ValueError("categorical probability rows do not match prediction_length")
        for row in self.categorical_probabilities:
            if len(row) != len(self.alphabet):
                raise ValueError("categorical probability width does not match alphabet")
            if any(not math.isfinite(value) for value in row):
                raise ValueError("categorical probabilities must be finite")
            if any(value < 0.0 or value > 1.0 for value in row):
                raise ValueError("categorical probabilities must lie in [0, 1]")
            if not math.isclose(sum(row), 1.0, rel_tol=0.0, abs_tol=1e-9):
                raise ValueError("categorical probability rows must sum to one")
        for sample in self.samples:
            if len(sample) != self.prediction_length:
                raise ValueError("sample horizon does not match prediction_length")
            if any(symbol not in self.alphabet for symbol in sample):
                raise ValueError("samples contain a symbol outside the alphabet")
        return self


class BayesianContextTreeStateManifestV1(_BayesianContextTreeIdentityV1):
    implementation_status: Literal["CONTRACT_ONLY"] = "CONTRACT_ONLY"
    state_sha256: str
    state_format: Literal["json+npz"] = "json+npz"
    persisted_at: datetime
    artifact_paths: list[str]

    @field_validator("state_sha256")
    @classmethod
    def validate_state_sha256(cls, value: str) -> str:
        return _validate_sha256(value)

    @field_validator("artifact_paths")
    @classmethod
    def validate_state_artifact_paths(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("state artifact_paths must not be empty")
        if len(value) != len(set(value)):
            raise ValueError("state artifact_paths must not contain duplicates")
        return [_validate_relative_artifact_path(path) for path in value]

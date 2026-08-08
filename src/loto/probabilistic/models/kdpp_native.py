from __future__ import annotations

import hashlib
import json
import math
import re
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MODEL_ID = "pp-k-dpp-fixed-k"
GRAPH_ID = "k_dpp_fixed_k_v1"
MODEL_REVISION = "k_dpp_fixed_k_v1"
SCHEMA_VERSION = "1.0.0"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
POSITION_ITEM_PATTERN = re.compile(r"^n([1-4]):([0-9])$")


class KDPPExecutionPending(RuntimeError):
    """Raised when a PR-B runtime operation is requested from the PR-A skeleton."""


class KDPPGame(StrEnum):
    NUMBERS3 = "numbers3"
    NUMBERS4 = "numbers4"
    MINILOTO = "miniloto"
    LOTO6 = "loto6"
    LOTO7 = "loto7"


class KDPPTargetLayout(StrEnum):
    POSITION_LOCAL = "position_local"
    POSITION_QUALIFIED_SHARED = "position_qualified_shared"
    UNORDERED_FIXED_CARDINALITY = "unordered_fixed_cardinality"


class KDPPKernelType(StrEnum):
    L_ENSEMBLE = "L_ENSEMBLE"


class KDPPPSDRepairPolicy(StrEnum):
    REJECT = "REJECT"


class KDPPPointForecastSemantics(StrEnum):
    SEEDED_EXACT_SAMPLE = "SEEDED_EXACT_KDPP_SAMPLE"


class KDPPDegeneracyStatus(StrEnum):
    DIVERSE_KERNEL = "DIVERSE_KERNEL"
    DEGENERATE = "DEGENERATE_TO_CONDITIONAL_BERNOULLI"


class StrictContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        allow_inf_nan=False,
        validate_default=True,
    )


class KDPPChronologyEvidence(StrictContract):
    train_start: int = Field(ge=0)
    train_end: int = Field(ge=0)
    validation_start: int | None = Field(default=None, ge=0)
    validation_end: int | None = Field(default=None, ge=0)
    forecast_origin: int = Field(ge=0)
    future_actuals_available: Literal[False] = False
    known_future_covariates: tuple[str, ...] = ()
    feature_cutoff: int = Field(ge=0)
    feature_matrix_sha256: str

    @field_validator("feature_matrix_sha256")
    @classmethod
    def validate_feature_hash(cls, value: str) -> str:
        return _validate_sha256(value, "feature_matrix_sha256")

    @model_validator(mode="after")
    def validate_order(self) -> KDPPChronologyEvidence:
        if self.train_start > self.train_end:
            raise ValueError("train_start must not exceed train_end")
        if self.feature_cutoff != self.train_end:
            raise ValueError("feature_cutoff must equal train_end")
        if self.forecast_origin <= self.train_end:
            raise ValueError("forecast_origin must be after train_end")
        if (self.validation_start is None) != (self.validation_end is None):
            raise ValueError("validation_start and validation_end must be supplied together")
        if self.validation_start is not None and self.validation_end is not None:
            if self.validation_start <= self.train_end:
                raise ValueError("validation_start must be after train_end")
            if self.validation_start > self.validation_end:
                raise ValueError("validation_start must not exceed validation_end")
            if self.forecast_origin <= self.validation_end:
                raise ValueError("forecast_origin must be after validation_end")
        return self


class KDPPFixedKConfig(StrictContract):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    model_id: Literal[MODEL_ID] = MODEL_ID
    graph_id: Literal[GRAPH_ID] = GRAPH_ID
    model_revision: Literal[MODEL_REVISION] = MODEL_REVISION
    public_registration: Literal[False] = False
    runtime_status: Literal["EXECUTION_PENDING"] = "EXECUTION_PENDING"
    comparison_model: Literal["pp-conditional-bernoulli-fixed-k"] = (
        "pp-conditional-bernoulli-fixed-k"
    )
    kernel_type: Literal[KDPPKernelType.L_ENSEMBLE] = KDPPKernelType.L_ENSEMBLE
    psd_tolerance: float = Field(default=1e-10, gt=0.0, le=1e-3)
    psd_repair_policy: Literal[KDPPPSDRepairPolicy.REJECT] = KDPPPSDRepairPolicy.REJECT
    supported_games: tuple[KDPPGame, ...] = (
        KDPPGame.NUMBERS3,
        KDPPGame.NUMBERS4,
        KDPPGame.MINILOTO,
        KDPPGame.LOTO6,
        KDPPGame.LOTO7,
    )
    supported_prediction_lengths: tuple[Literal[1, 2, 5], ...] = (1, 2, 5)
    requested_device: Literal["cpu"] = "cpu"
    quantiles_supported: Literal[False] = False
    default_point_forecast_semantics: Literal[KDPPPointForecastSemantics.SEEDED_EXACT_SAMPLE] = (
        KDPPPointForecastSemantics.SEEDED_EXACT_SAMPLE
    )

    @field_validator("supported_games", mode="before")
    @classmethod
    def normalize_games(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(KDPPGame(item) if isinstance(item, str) else item for item in value)
        return value

    @field_validator("supported_games")
    @classmethod
    def validate_games(cls, value: tuple[KDPPGame, ...]) -> tuple[KDPPGame, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("supported_games must be non-empty and unique")
        return value

    @field_validator("supported_prediction_lengths", mode="before")
    @classmethod
    def normalize_horizons(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("supported_prediction_lengths")
    @classmethod
    def validate_horizons(cls, value: tuple[Literal[1, 2, 5], ...]) -> tuple[Literal[1, 2, 5], ...]:
        if tuple(value) != (1, 2, 5):
            raise ValueError("supported_prediction_lengths must be exactly (1, 2, 5)")
        return value


class KDPPFixedKRequest(StrictContract):
    schema_version: Literal[SCHEMA_VERSION]
    run_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    model_id: Literal[MODEL_ID]
    package_version: str = Field(min_length=1, max_length=64)
    source_revision: str
    model_revision: Literal[MODEL_REVISION]
    config_sha256: str
    weight_sha256: str | None = None
    license: Literal["MIT"]
    game: KDPPGame
    target_layout: KDPPTargetLayout
    context_length: int = Field(ge=1, le=1_000_000)
    prediction_length: Literal[1, 2, 5]
    seed: int = Field(ge=0, le=2**32 - 1)
    requested_device: Literal["cpu"]
    chronology_evidence: KDPPChronologyEvidence
    actuals_used: Literal[False]
    kernel_type: Literal[KDPPKernelType.L_ENSEMBLE]
    kernel_shape: tuple[int, int]
    kernel_sha256: str
    item_ids: tuple[str, ...]
    cardinality: int = Field(ge=1)
    psd_tolerance: float = Field(gt=0.0, le=1e-3)
    psd_repair_policy: Literal[KDPPPSDRepairPolicy.REJECT]

    @field_validator("source_revision")
    @classmethod
    def validate_source_revision(cls, value: str) -> str:
        if not GIT_SHA_PATTERN.fullmatch(value):
            raise ValueError("source_revision must be a 40-character lowercase Git SHA")
        return value

    @field_validator("config_sha256", "kernel_sha256")
    @classmethod
    def validate_hashes(cls, value: str, info: Any) -> str:
        return _validate_sha256(value, info.field_name)

    @field_validator("weight_sha256")
    @classmethod
    def validate_optional_weight_hash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_sha256(value, "weight_sha256")

    @field_validator("item_ids")
    @classmethod
    def validate_item_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) < 2:
            raise ValueError("item_ids must contain at least two candidates")
        if any(not item or item.strip() != item for item in value):
            raise ValueError("item_ids must be non-empty normalized strings")
        if len(value) != len(set(value)):
            raise ValueError("item_ids must be unique by full item identity")
        return value

    @model_validator(mode="after")
    def validate_geometry(self) -> KDPPFixedKRequest:
        candidate_count = len(self.item_ids)
        if self.kernel_shape != (candidate_count, candidate_count):
            raise ValueError("kernel_shape must equal (len(item_ids), len(item_ids))")
        if self.cardinality >= candidate_count:
            raise ValueError("cardinality must be smaller than the candidate count")
        _validate_game_geometry(
            game=self.game,
            target_layout=self.target_layout,
            item_ids=self.item_ids,
            cardinality=self.cardinality,
        )
        return self


class KDPPFixedKResponse(StrictContract):
    schema_version: Literal[SCHEMA_VERSION]
    run_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    model_id: Literal[MODEL_ID]
    package_version: str = Field(min_length=1, max_length=64)
    source_revision: str
    model_revision: Literal[MODEL_REVISION]
    config_sha256: str
    weight_sha256: str
    license: Literal["MIT"]
    game: KDPPGame
    target_layout: KDPPTargetLayout
    context_length: int = Field(ge=1, le=1_000_000)
    prediction_length: Literal[1, 2, 5]
    seed: int = Field(ge=0, le=2**32 - 1)
    requested_device: Literal["cpu"]
    effective_device: Literal["cpu"]
    cpu_fallback: Literal[False]
    input_shape: tuple[int, int]
    output_shape: tuple[int, int]
    point_forecast: tuple[tuple[str, ...], ...]
    quantiles: None = None
    samples: tuple[tuple[tuple[str, ...], ...], ...]
    finite_check: Literal[True]
    chronology_evidence: KDPPChronologyEvidence
    actuals_used: Literal[False]
    runtime_pid: int = Field(ge=1)
    gpu_uuid: None = None
    gpu_process_vram_mb: None = None
    gpu_not_applicable: Literal[True]
    artifact_paths: tuple[str, ...]
    kernel_type: Literal[KDPPKernelType.L_ENSEMBLE]
    kernel_shape: tuple[int, int]
    kernel_sha256: str
    item_ids: tuple[str, ...]
    cardinality: int = Field(ge=1)
    psd_tolerance: float = Field(gt=0.0, le=1e-3)
    psd_repair_policy: Literal[KDPPPSDRepairPolicy.REJECT]
    symmetry_check: Literal[True]
    psd_check: Literal[True]
    minimum_eigenvalue: float
    kernel_rank: int = Field(ge=1)
    effective_rank: float = Field(gt=0.0)
    log_normalizer: float
    kernel_off_diagonal_norm: float = Field(ge=0.0)
    kernel_off_diagonal_ratio: float = Field(ge=0.0, le=1.0)
    degeneracy_status: KDPPDegeneracyStatus
    marginal_inclusion_probabilities: tuple[tuple[float, ...], ...]
    exact_cardinality_check: Literal[True]
    duplicate_check: Literal[True]
    point_forecast_semantics: Literal[KDPPPointForecastSemantics.SEEDED_EXACT_SAMPLE]

    @field_validator("source_revision")
    @classmethod
    def validate_source_revision(cls, value: str) -> str:
        if not GIT_SHA_PATTERN.fullmatch(value):
            raise ValueError("source_revision must be a 40-character lowercase Git SHA")
        return value

    @field_validator("config_sha256", "weight_sha256", "kernel_sha256")
    @classmethod
    def validate_hashes(cls, value: str, info: Any) -> str:
        return _validate_sha256(value, info.field_name)

    @field_validator("artifact_paths")
    @classmethod
    def validate_artifact_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("artifact_paths must not be empty")
        if len(value) != len(set(value)):
            raise ValueError("artifact_paths must not contain duplicates")
        for raw_path in value:
            path = PurePosixPath(raw_path)
            if path.is_absolute() or not path.parts or ".." in path.parts or "." in path.parts:
                raise ValueError("artifact_paths must be normalized safe relative paths")
            if "\\" in raw_path:
                raise ValueError("artifact_paths must use POSIX separators")
        return value

    @model_validator(mode="after")
    def validate_output(self) -> KDPPFixedKResponse:
        candidate_count = len(self.item_ids)
        if self.kernel_shape != (candidate_count, candidate_count):
            raise ValueError("kernel_shape must match item_ids")
        if self.input_shape != self.kernel_shape:
            raise ValueError("input_shape must match kernel_shape")
        if self.output_shape != (self.prediction_length, self.cardinality):
            raise ValueError("output_shape must equal (prediction_length, cardinality)")
        if len(self.point_forecast) != self.prediction_length:
            raise ValueError("point_forecast must contain one subset per horizon step")
        if len(self.samples) != self.prediction_length:
            raise ValueError("samples must contain one sample collection per horizon step")
        if len(self.marginal_inclusion_probabilities) != self.prediction_length:
            raise ValueError("marginals must contain one row per horizon step")
        item_set = set(self.item_ids)
        for subset in self.point_forecast:
            _validate_subset(subset, self.cardinality, item_set, "point_forecast")
        for horizon_samples in self.samples:
            if not horizon_samples:
                raise ValueError("each horizon step must contain at least one sample")
            for subset in horizon_samples:
                _validate_subset(subset, self.cardinality, item_set, "samples")
        for probabilities in self.marginal_inclusion_probabilities:
            if len(probabilities) != candidate_count:
                raise ValueError("marginal probability width must match item_ids")
            if any(
                not math.isfinite(value) or value < 0.0 or value > 1.0 for value in probabilities
            ):
                raise ValueError("marginal probabilities must be finite values in [0, 1]")
            if not math.isclose(sum(probabilities), self.cardinality, abs_tol=1e-8):
                raise ValueError("marginal probabilities must sum to cardinality")
        finite_scalars = (
            self.minimum_eigenvalue,
            self.effective_rank,
            self.log_normalizer,
            self.kernel_off_diagonal_norm,
            self.kernel_off_diagonal_ratio,
            self.psd_tolerance,
        )
        if not all(math.isfinite(value) for value in finite_scalars):
            raise ValueError("numeric evidence must be finite")
        if self.kernel_rank < self.cardinality:
            raise ValueError("kernel_rank must be at least cardinality")
        expected_degeneracy = (
            KDPPDegeneracyStatus.DEGENERATE
            if self.kernel_off_diagonal_norm == 0.0 or self.kernel_off_diagonal_ratio == 0.0
            else KDPPDegeneracyStatus.DIVERSE_KERNEL
        )
        if self.degeneracy_status != expected_degeneracy:
            raise ValueError("degeneracy_status disagrees with off-diagonal evidence")
        _validate_game_geometry(
            game=self.game,
            target_layout=self.target_layout,
            item_ids=self.item_ids,
            cardinality=self.cardinality,
        )
        return self


def _validate_sha256(value: str, field_name: str) -> str:
    if not SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a 64-character lowercase SHA-256")
    return value


def _validate_subset(
    subset: tuple[str, ...],
    cardinality: int,
    item_set: set[str],
    field_name: str,
) -> None:
    if len(subset) != cardinality or len(set(subset)) != cardinality:
        raise ValueError(f"{field_name} subset must have exact cardinality and no duplicates")
    if not set(subset).issubset(item_set):
        raise ValueError(f"{field_name} contains an unknown item")


def _validate_game_geometry(
    *,
    game: KDPPGame,
    target_layout: KDPPTargetLayout,
    item_ids: tuple[str, ...],
    cardinality: int,
) -> None:
    if game in {KDPPGame.NUMBERS3, KDPPGame.NUMBERS4}:
        allowed_positions = 3 if game is KDPPGame.NUMBERS3 else 4
        matches = [POSITION_ITEM_PATTERN.fullmatch(item) for item in item_ids]
        if any(match is None for match in matches):
            raise ValueError(
                "Numbers3/4 item IDs must be position-qualified as n<position>:<digit>"
            )
        positions = {int(match.group(1)) for match in matches if match is not None}
        if any(position < 1 or position > allowed_positions for position in positions):
            raise ValueError("position-qualified item exceeds the game position count")
        if target_layout is KDPPTargetLayout.POSITION_LOCAL:
            if cardinality != 1 or len(positions) != 1:
                raise ValueError(
                    "position_local Numbers3/4 requires one position and cardinality=1"
                )
        elif target_layout is KDPPTargetLayout.POSITION_QUALIFIED_SHARED:
            if cardinality != allowed_positions:
                raise ValueError("shared Numbers3/4 cardinality must equal the position count")
            if positions != set(range(1, allowed_positions + 1)):
                raise ValueError("shared Numbers3/4 item IDs must cover every position")
        else:
            raise ValueError("Numbers3/4 requires a position-qualified layout")
        return

    expected_cardinality = {
        KDPPGame.MINILOTO: 5,
        KDPPGame.LOTO6: 6,
        KDPPGame.LOTO7: 7,
    }[game]
    if target_layout is not KDPPTargetLayout.UNORDERED_FIXED_CARDINALITY:
        raise ValueError("MiniLoto/Loto6/Loto7 require unordered_fixed_cardinality")
    if cardinality != expected_cardinality:
        raise ValueError(f"{game.value} requires cardinality={expected_cardinality}")


def canonical_config_sha256(value: KDPPFixedKConfig | dict[str, Any]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, KDPPFixedKConfig) else value
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_kdpp_fixed_k_config(path: str | Path) -> KDPPFixedKConfig:
    source = Path(path)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("k-DPP config must be a YAML mapping")
    return KDPPFixedKConfig.model_validate(payload)


class KDPPFixedKModelSkeleton:
    """Private PR-A skeleton. Fit, predict and persistence intentionally fail closed."""

    model_id = MODEL_ID
    graph_id = GRAPH_ID
    model_revision = MODEL_REVISION
    public_registration = False
    runtime_status = "EXECUTION_PENDING"
    reused_math_modules = (
        "loto.probabilistic.math.kdpp",
        "loto.probabilistic.math.psd",
        "loto.probabilistic.math.elementary_symmetric",
        "loto.probabilistic.math.logspace_dp",
    )

    def fit(self, *_: Any, **__: Any) -> None:
        raise KDPPExecutionPending("k-DPP fit is deferred to PR-B runtime implementation")

    def predict(self, *_: Any, **__: Any) -> None:
        raise KDPPExecutionPending("k-DPP prediction is deferred to PR-B runtime implementation")

    def save(self, *_: Any, **__: Any) -> None:
        raise KDPPExecutionPending("k-DPP state persistence is deferred to PR-B")

    @classmethod
    def load(cls, *_: Any, **__: Any) -> KDPPFixedKModelSkeleton:
        raise KDPPExecutionPending("k-DPP state reload is deferred to PR-B")

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

from .geometry import GameGeometry
from .manifests import (
    PACKAGE_MANIFEST,
    TABPFN_TS_PACKAGE_VERSION,
    CheckpointLane,
    ExecutionStatus,
    V2_REPO_ID,
    V2_REVISION,
    lane_manifest,
)

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
Probability = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
QuantileLevel = Annotated[float, Field(gt=0.0, lt=1.0, allow_inf_nan=False)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Operation(StrEnum):
    PREDICT = "predict"


class ModelFamily(StrEnum):
    TABPFN_TS = "tabpfn-ts"


class TaskFormulation(StrEnum):
    POSITION_LOCAL = "position_local"
    POSITION_BATCH = "position_batch"
    CANDIDATE_SCORE = "candidate_score"


class TimeSemantics(StrEnum):
    DRAW_SEQUENCE = "draw_sequence"
    CALENDAR_TIME = "calendar_time"


class OutputSelection(StrEnum):
    MEAN = "mean"
    MEDIAN = "median"
    MODE = "mode"


class Device(StrEnum):
    CPU = "cpu"
    CUDA = "cuda"


class ResponseStatus(StrEnum):
    OK = "OK"
    BLOCKED = "BLOCKED"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    FAILED_CPU_FALLBACK = "FAILED_CPU_FALLBACK"
    MODEL_WEIGHTS_MISSING = "MODEL_WEIGHTS_MISSING"
    CHECKPOINT_HASH_MISMATCH = "CHECKPOINT_HASH_MISMATCH"
    UNSUPPORTED_BY_UPSTREAM = "UNSUPPORTED_BY_UPSTREAM"


class HistorySeries(StrictModel):
    series_id: NonEmptyString
    timestamps: list[NonEmptyString]
    values: list[FiniteFloat]

    @model_validator(mode="after")
    def validate_lengths(self) -> HistorySeries:
        if not self.timestamps:
            raise ValueError("history timestamps must not be empty")
        if len(self.timestamps) != len(self.values):
            raise ValueError("history timestamps and values must have identical lengths")
        if len(set(self.timestamps)) != len(self.timestamps):
            raise ValueError("history timestamps must be unique within each series")
        return self


class KnownFutureCovariateRow(StrictModel):
    horizon_step: int = Field(ge=1)
    timestamp: NonEmptyString
    values: dict[NonEmptyString, JsonValue]
    series_id: NonEmptyString | None = None

    @field_validator("values")
    @classmethod
    def reject_empty_values(cls, values: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if not values:
            raise ValueError("known-future covariate values must not be empty")
        return values


class TabPFNTSRequestV2(StrictModel):
    schema_version: Literal[2] = 2
    run_id: NonEmptyString
    operation: Literal[Operation.PREDICT] = Operation.PREDICT
    model_family: Literal[ModelFamily.TABPFN_TS] = ModelFamily.TABPFN_TS
    checkpoint_lane: CheckpointLane
    repo_id: NonEmptyString | None = None
    revision: NonEmptyString | None = None
    task_formulation: TaskFormulation
    game_geometry: GameGeometry
    series_ids: list[NonEmptyString]
    history: list[HistorySeries]
    known_future_covariates: list[KnownFutureCovariateRow] = Field(default_factory=list)
    past_only_covariates: list[dict[str, JsonValue]] = Field(default_factory=list)
    static_covariates: dict[str, JsonValue] = Field(default_factory=dict)
    time_semantics: TimeSemantics
    feature_set_id: NonEmptyString
    max_context_length: int = Field(ge=1, le=32_768)
    prediction_length: Literal[1, 2, 5]
    quantile_levels: list[QuantileLevel] = Field(default_factory=lambda: [0.1, 0.5, 0.9])
    output_selection: OutputSelection = OutputSelection.MEDIAN
    device: Device
    seed: int = 1
    local_files_only: Literal[True] = True
    offline_required: Literal[True] = True
    telemetry_disabled: Literal[True] = True
    network_access: Literal[False] = False
    tabpfn_mode: Literal["LOCAL"] = "LOCAL"
    package_version: Literal[TABPFN_TS_PACKAGE_VERSION] = TABPFN_TS_PACKAGE_VERSION

    @field_validator("series_ids")
    @classmethod
    def validate_series_ids(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("series_ids must not be empty")
        if len(set(values)) != len(values):
            raise ValueError("series_ids must be unique")
        return values

    @field_validator("quantile_levels")
    @classmethod
    def validate_quantile_levels(cls, values: list[float]) -> list[float]:
        if not values:
            raise ValueError("quantile_levels must not be empty")
        if values != sorted(set(values)):
            raise ValueError("quantile_levels must be strictly increasing and unique")
        return values

    @model_validator(mode="after")
    def validate_contract(self) -> TabPFNTSRequestV2:
        if self.past_only_covariates:
            raise ValueError("UNSUPPORTED_BY_UPSTREAM: past-only covariates")
        if self.static_covariates:
            raise ValueError("UNSUPPORTED_BY_UPSTREAM: static covariates")

        history_ids = [series.series_id for series in self.history]
        if history_ids != self.series_ids:
            raise ValueError("history series order must exactly match series_ids")
        reference_timestamps = self.history[0].timestamps
        if any(series.timestamps != reference_timestamps for series in self.history[1:]):
            raise ValueError("all history series must share identical timestamp identity")

        expected_series_count = (
            self.game_geometry.candidate_count
            if self.task_formulation is TaskFormulation.CANDIDATE_SCORE
            else self.game_geometry.position_count
        )
        if len(self.series_ids) != expected_series_count:
            raise ValueError(
                "series count does not match task formulation and game geometry: "
                f"expected={expected_series_count}, actual={len(self.series_ids)}"
            )

        if self.task_formulation is TaskFormulation.CANDIDATE_SCORE:
            if not self.game_geometry.strictly_increasing:
                raise ValueError(
                    "candidate_score requires a strictly increasing unique-selection game"
                )
            if self.prediction_length != 1:
                raise ValueError(
                    "legacy candidate_score contract supports prediction_length=1 only"
                )

        covariate_keys = [
            (row.series_id, row.horizon_step) for row in self.known_future_covariates
        ]
        if len(covariate_keys) != len(set(covariate_keys)):
            raise ValueError("known-future covariate rows must be unique per series/horizon")

        for row in self.known_future_covariates:
            if row.horizon_step > self.prediction_length:
                raise ValueError("known-future covariate exceeds prediction_length")
            if row.series_id is not None and row.series_id not in self.series_ids:
                raise ValueError(f"unknown covariate series_id: {row.series_id}")

        if self.checkpoint_lane is CheckpointLane.V2_REG_LEGACY:
            if self.repo_id != V2_REPO_ID or self.revision != V2_REVISION:
                raise ValueError("legacy V2 lane requires the fixed repo_id and revision")
        return self


class ForecastValue(StrictModel):
    series_id: NonEmptyString
    horizon_step: int = Field(ge=1)
    value: FiniteFloat


class QuantileForecast(StrictModel):
    level: QuantileLevel
    values: list[ForecastValue]


class CandidateScore(StrictModel):
    candidate: int
    raw_candidate_regression_score: FiniteFloat


class CandidateProbability(StrictModel):
    candidate: int
    calibrated_probability: Probability


class ModelIdentity(StrictModel):
    model_family: Literal[ModelFamily.TABPFN_TS] = ModelFamily.TABPFN_TS
    checkpoint_lane: CheckpointLane
    package_version: Literal[TABPFN_TS_PACKAGE_VERSION] = TABPFN_TS_PACKAGE_VERSION
    repo_id: NonEmptyString | None = None
    revision: NonEmptyString | None = None
    checkpoint_filename: NonEmptyString
    checkpoint_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None


class EffectiveArguments(StrictModel):
    game_geometry: GameGeometry
    max_context_length: int = Field(ge=1, le=32_768)
    effective_context_length: int = Field(ge=1, le=32_768)
    prediction_length: Literal[1, 2, 5]
    quantile_levels: list[QuantileLevel]
    output_selection: OutputSelection
    feature_set_id: NonEmptyString
    time_semantics: TimeSemantics
    local_files_only: Literal[True] = True
    offline_required: Literal[True] = True
    telemetry_disabled: Literal[True] = True
    network_access: Literal[False] = False
    tabpfn_mode: Literal["LOCAL"] = "LOCAL"

    @field_validator("quantile_levels")
    @classmethod
    def validate_quantile_levels(cls, values: list[float]) -> list[float]:
        if not values:
            raise ValueError("quantile_levels must not be empty")
        if values != sorted(set(values)):
            raise ValueError("quantile_levels must be strictly increasing and unique")
        return values


class FeatureManifest(StrictModel):
    feature_set_id: NonEmptyString
    generators: list[NonEmptyString]
    config_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    frequency_policy: NonEmptyString
    missing_period_policy: NonEmptyString
    timestamp_mapping_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None


class RuntimeEvidence(StrictModel):
    provider_pid: int = Field(ge=1)
    separate_process_reload: bool
    reload_status: NonEmptyString
    local_files_only: Literal[True] = True
    telemetry_disabled: Literal[True] = True
    network_access: Literal[False] = False
    model_parameter_device: NonEmptyString | None = None
    training_table_device: NonEmptyString | None = None
    test_table_device: NonEmptyString | None = None
    prediction_tensor_device: NonEmptyString | None = None


class GPUEvidence(StrictModel):
    requested_device: Device
    effective_device: Device
    model_parameter_device: NonEmptyString | None = None
    training_table_device: NonEmptyString | None = None
    test_table_device: NonEmptyString | None = None
    prediction_tensor_device: NonEmptyString | None = None
    provider_pid: int = Field(ge=1)
    gpu_uuid: NonEmptyString | None = None
    vram_before_bytes: int = Field(ge=0)
    vram_peak_bytes: int = Field(ge=0)
    vram_after_bytes: int = Field(ge=0)
    cpu_fallback: bool

    @model_validator(mode="after")
    def validate_vram(self) -> GPUEvidence:
        if self.vram_peak_bytes < self.vram_before_bytes:
            raise ValueError("vram_peak_bytes must be >= vram_before_bytes")
        return self


class ArtifactReference(StrictModel):
    provider_manifest_path: NonEmptyString | None = None
    checkpoint_path: NonEmptyString | None = None
    weight_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    config_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    prediction_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None


class LicenseEvidence(StrictModel):
    code_license: NonEmptyString
    weight_license: NonEmptyString | None
    attribution_required: bool | None
    license_accepted: bool
    production_champion_eligible: bool
    pretraining_data_overlap: Literal["UNKNOWN"] = "UNKNOWN"


class TabPFNTSResponseV2(StrictModel):
    schema_version: Literal[2] = 2
    status: ResponseStatus
    model_identity: ModelIdentity
    effective_arguments: EffectiveArguments
    task_formulation: TaskFormulation
    point_forecast: list[ForecastValue] = Field(default_factory=list)
    point_method: OutputSelection
    quantiles: list[QuantileForecast] = Field(default_factory=list)
    raw_candidate_scores: list[CandidateScore] | None = None
    calibrated_candidate_probabilities: list[CandidateProbability] | None = None
    selected_candidates: list[int] | None = None
    series_identity: list[NonEmptyString]
    prediction_index: list[int]
    feature_manifest: FeatureManifest
    runtime_evidence: RuntimeEvidence
    gpu_evidence: GPUEvidence
    artifact_reference: ArtifactReference
    license_evidence: LicenseEvidence
    warnings: list[str] = Field(default_factory=list)
    unsupported_arguments: list[str] = Field(default_factory=list)

    @field_validator("series_identity")
    @classmethod
    def validate_series_identity(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("series_identity must be unique")
        return values

    @field_validator("prediction_index")
    @classmethod
    def validate_prediction_index(cls, values: list[int]) -> list[int]:
        if values != list(range(1, len(values) + 1)):
            raise ValueError("prediction_index must be contiguous and 1-based")
        return values

    @model_validator(mode="after")
    def validate_outputs(self) -> TabPFNTSResponseV2:
        expected_index = list(range(1, self.effective_arguments.prediction_length + 1))
        if self.prediction_index != expected_index:
            raise ValueError("prediction_index does not match prediction_length")

        if self.status is ResponseStatus.OK:
            self._validate_provenance()
            self._validate_gpu_success()
            self._validate_runtime_identity()
            self._validate_task_outputs()
            self._validate_quantiles()
        return self

    def _validate_provenance(self) -> None:
        identity = self.model_identity
        manifest = lane_manifest(identity.checkpoint_lane)
        if manifest.execution_status is not ExecutionStatus.READY:
            raise ValueError(
                f"BLOCKED: checkpoint lane is not executable: {manifest.execution_status.value}"
            )
        expected_identity = (
            manifest.repo_id,
            manifest.revision,
            manifest.filename,
            manifest.sha256,
        )
        actual_identity = (
            identity.repo_id,
            identity.revision,
            identity.checkpoint_filename,
            identity.checkpoint_sha256,
        )
        if actual_identity != expected_identity:
            raise ValueError("model identity does not match the executable lane manifest")
        if self.artifact_reference.weight_sha256 != identity.checkpoint_sha256:
            raise ValueError("artifact weight_sha256 does not match model identity")
        if self.license_evidence.code_license != PACKAGE_MANIFEST.code_license:
            raise ValueError("code license does not match the package manifest")
        if self.license_evidence.weight_license != manifest.weight_license:
            raise ValueError("weight license does not match the checkpoint manifest")
        if self.license_evidence.attribution_required != manifest.attribution_required:
            raise ValueError("attribution requirement does not match the checkpoint manifest")
        if manifest.license_acceptance_required and not self.license_evidence.license_accepted:
            raise ValueError("checkpoint license acceptance is required for status=OK")
        if (
            self.license_evidence.production_champion_eligible
            != manifest.production_champion_eligible
        ):
            raise ValueError("production eligibility does not match the checkpoint manifest")

    def _validate_runtime_identity(self) -> None:
        if self.feature_manifest.feature_set_id != self.effective_arguments.feature_set_id:
            raise ValueError("feature_set_id differs between arguments and feature manifest")
        if self.runtime_evidence.provider_pid != self.gpu_evidence.provider_pid:
            raise ValueError("provider PID differs between runtime and GPU evidence")
        device_fields = (
            "model_parameter_device",
            "training_table_device",
            "test_table_device",
            "prediction_tensor_device",
        )
        for field_name in device_fields:
            runtime_value = getattr(self.runtime_evidence, field_name)
            gpu_value = getattr(self.gpu_evidence, field_name)
            if runtime_value != gpu_value:
                raise ValueError(f"{field_name} differs between runtime and GPU evidence")

    def _validate_gpu_success(self) -> None:
        evidence = self.gpu_evidence
        if evidence.requested_device is not evidence.effective_device or evidence.cpu_fallback:
            raise ValueError("FAILED_CPU_FALLBACK: effective device differs from request")
        if evidence.requested_device is Device.CUDA:
            device_values = [
                evidence.model_parameter_device,
                evidence.training_table_device,
                evidence.test_table_device,
                evidence.prediction_tensor_device,
            ]
            if any(value is None or not value.startswith("cuda") for value in device_values):
                raise ValueError("GPU evidence is incomplete for a successful CUDA response")
            if evidence.gpu_uuid is None:
                raise ValueError("GPU UUID is required for a successful CUDA response")

    def _expected_pairs(self) -> set[tuple[str, int]]:
        return {
            (series_id, horizon_step)
            for series_id in self.series_identity
            for horizon_step in self.prediction_index
        }

    def _validate_task_outputs(self) -> None:
        geometry = self.effective_arguments.game_geometry
        if self.task_formulation in {
            TaskFormulation.POSITION_LOCAL,
            TaskFormulation.POSITION_BATCH,
        }:
            if len(self.series_identity) != geometry.position_count:
                raise ValueError("position response series count does not match game geometry")
            point_pairs = {(item.series_id, item.horizon_step) for item in self.point_forecast}
            if (
                point_pairs != self._expected_pairs()
                or len(self.point_forecast) != len(point_pairs)
            ):
                raise ValueError(
                    "point forecast must cover every series/horizon pair exactly once"
                )
            if self.raw_candidate_scores is not None:
                raise ValueError("position response must not contain candidate scores")
        else:
            if not geometry.strictly_increasing:
                raise ValueError(
                    "candidate-score response requires a strictly increasing game geometry"
                )
            if self.effective_arguments.prediction_length != 1:
                raise ValueError(
                    "legacy candidate-score response supports prediction_length=1 only"
                )
            if len(self.series_identity) != geometry.candidate_count:
                raise ValueError("candidate response series count does not match game geometry")
            if self.raw_candidate_scores is None:
                raise ValueError("candidate-score response requires raw_candidate_scores")
            candidates = [item.candidate for item in self.raw_candidate_scores]
            expected_candidates = list(
                range(geometry.candidate_min, geometry.candidate_max + 1)
            )
            if sorted(candidates) != expected_candidates or len(set(candidates)) != len(candidates):
                raise ValueError("raw candidate scores must cover the full candidate universe")

            if self.calibrated_candidate_probabilities is not None:
                probability_candidates = [
                    item.candidate for item in self.calibrated_candidate_probabilities
                ]
                if (
                    sorted(probability_candidates) != expected_candidates
                    or len(set(probability_candidates)) != len(probability_candidates)
                ):
                    raise ValueError(
                        "calibrated probabilities must cover the candidate universe exactly once"
                    )
                total = sum(
                    item.calibrated_probability
                    for item in self.calibrated_candidate_probabilities
                )
                if not math.isclose(total, geometry.selection_count, abs_tol=1e-3):
                    raise ValueError(
                        "calibrated probability sum must approximate selection_count"
                    )

            if self.selected_candidates is not None:
                if self.selected_candidates != sorted(self.selected_candidates):
                    raise ValueError("selected_candidates must be sorted into position order")
                if len(self.selected_candidates) != geometry.selection_count:
                    raise ValueError("selected_candidates length must equal selection_count")
                geometry.validate_positions(self.selected_candidates)

    def _validate_quantiles(self) -> None:
        if not self.quantiles:
            return
        levels = [quantile.level for quantile in self.quantiles]
        if levels != sorted(set(levels)):
            raise ValueError("response quantile levels must be strictly increasing and unique")
        if levels != self.effective_arguments.quantile_levels:
            raise ValueError("response quantile levels do not match effective arguments")

        expected_pairs = self._expected_pairs()
        by_level: dict[float, dict[tuple[str, int], float]] = {}
        for quantile in self.quantiles:
            mapping = {
                (value.series_id, value.horizon_step): value.value
                for value in quantile.values
            }
            if set(mapping) != expected_pairs or len(quantile.values) != len(mapping):
                raise ValueError(
                    "quantile forecast shape does not match series/horizon identity "
                    "exactly once"
                )
            by_level[quantile.level] = mapping

        for pair in expected_pairs:
            values = [by_level[level][pair] for level in levels]
            if values != sorted(values):
                raise ValueError(f"quantile crossing detected for {pair}")

from __future__ import annotations

import hashlib
import importlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .argument_validator import classify_arguments
from .protocol import GameGeometry
from .timeseries_adapter import (
    build_position_local,
    build_position_multivariate,
    to_darts_local,
    to_darts_multivariate,
)
from .torch_models import (
    TorchDeviceContract,
    TorchRuntimeObservation,
    certify_device_use,
)

FOUNDATION_MODEL_IDENTITIES = (
    "Chronos2Model",
    "TimesFM2p5Model",
    "TiRexModel",
    "PatchTSTFMModel",
)
UNRESOLVED_REVISIONS = {
    "UNRESOLVED",
    "PIN_REQUIRED",
    "PIN_REQUIRED_BEFORE_EXECUTION",
}


class FoundationCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    supports_past_covariates: bool
    supports_future_covariates: bool
    supports_multivariate: bool
    supports_probabilistic_prediction: bool
    supports_finetuning: bool
    supports_full_finetuning: bool
    requires_license_acceptance: bool = False
    max_input_chunk_length: int | None = Field(default=None, ge=1)
    max_output_plus_shift: int | None = Field(default=None, ge=1)


FOUNDATION_CAPABILITIES: dict[str, FoundationCapability] = {
    "Chronos2Model": FoundationCapability(
        supports_past_covariates=True,
        supports_future_covariates=True,
        supports_multivariate=True,
        supports_probabilistic_prediction=True,
        supports_finetuning=True,
        supports_full_finetuning=True,
        max_input_chunk_length=8192,
        max_output_plus_shift=1024,
    ),
    "TimesFM2p5Model": FoundationCapability(
        supports_past_covariates=False,
        supports_future_covariates=False,
        supports_multivariate=True,
        supports_probabilistic_prediction=True,
        supports_finetuning=True,
        supports_full_finetuning=True,
        max_input_chunk_length=16384,
    ),
    "TiRexModel": FoundationCapability(
        supports_past_covariates=False,
        supports_future_covariates=False,
        supports_multivariate=True,
        supports_probabilistic_prediction=True,
        supports_finetuning=True,
        supports_full_finetuning=False,
        requires_license_acceptance=True,
        max_output_plus_shift=2048,
    ),
    "PatchTSTFMModel": FoundationCapability(
        supports_past_covariates=False,
        supports_future_covariates=False,
        supports_multivariate=True,
        supports_probabilistic_prediction=True,
        supports_finetuning=True,
        supports_full_finetuning=True,
        max_input_chunk_length=8192,
    ),
}

InputChunkLength = int | tuple[int, int]
FineTuningValue = bool | dict[str, list[str]]


class FoundationSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hub_model_name: str = Field(min_length=1)
    hub_model_revision: str = Field(min_length=1)
    local_dir: str | None = None
    allow_remote_download: bool = False

    @model_validator(mode="after")
    def validate_source(self) -> FoundationSourceConfig:
        if not self.allow_remote_download and not self.local_dir:
            raise ValueError("offline execution requires local_dir")
        return self

    @property
    def revision_is_resolved(self) -> bool:
        revision = self.hub_model_revision.lower()
        return (
            self.hub_model_revision not in UNRESOLVED_REVISIONS
            and len(revision) in {40, 64}
            and all(item in "0123456789abcdef" for item in revision)
        )


class FoundationModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    public_name: str
    source: FoundationSourceConfig
    model_args: dict[str, Any] = Field(default_factory=dict)
    accept_license: bool = False
    finetuning: FineTuningValue = False

    @model_validator(mode="after")
    def validate_model(self) -> FoundationModelConfig:
        if self.public_name not in FOUNDATION_MODEL_IDENTITIES:
            raise ValueError(f"unsupported foundation model: {self.public_name}")
        capability = FOUNDATION_CAPABILITIES[self.public_name]
        if capability.requires_license_acceptance and not self.accept_license:
            raise ValueError(f"{self.public_name} requires explicit license acceptance")
        if self.finetuning is True and not capability.supports_full_finetuning:
            raise ValueError(f"{self.public_name} does not support full fine-tuning")
        if isinstance(self.finetuning, dict):
            if set(self.finetuning) not in ({"freeze"}, {"unfreeze"}):
                raise ValueError("partial fine-tuning must contain freeze or unfreeze only")
            patterns = next(iter(self.finetuning.values()))
            if not patterns or any(not item.strip() for item in patterns):
                raise ValueError("partial fine-tuning patterns must be non-empty")
        if self.public_name == "TiRexModel" and self.finetuning:
            tirex = self.model_args.get("tirex_kwargs")
            if not isinstance(tirex, dict) or tirex.get("backend") != "torch":
                raise ValueError(
                    "TiRex fine-tuning requires tirex_kwargs.backend=torch"
                )
        return self


class FoundationCampaignConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    run_id: str = Field(min_length=1)
    track: Literal["zero_shot", "fine_tune"]
    models: tuple[FoundationModelConfig, ...]
    input_chunk_length: InputChunkLength
    output_chunk_length: int = Field(ge=1, le=8192)
    output_chunk_shift: int = Field(default=0, ge=0, le=8192)
    series_layout: Literal[
        "position_local",
        "position_multivariate",
        "position_global_sequence",
    ]
    horizon: int = Field(default=1, ge=1, le=8192)
    use_past_covariates: bool = False
    use_future_covariates: bool = False
    num_samples: int = Field(default=1, ge=1, le=100000)
    predict_likelihood_parameters: bool = False
    fit_args: dict[str, Any] = Field(default_factory=dict)
    predict_args: dict[str, Any] = Field(default_factory=dict)
    device: TorchDeviceContract = Field(default_factory=TorchDeviceContract)

    @field_validator("input_chunk_length")
    @classmethod
    def validate_input_chunk_length(
        cls,
        value: InputChunkLength,
    ) -> InputChunkLength:
        if isinstance(value, int):
            if value < 1:
                raise ValueError("input_chunk_length must be positive")
            return value
        if len(value) != 2 or value[0] < 1 or value[1] < value[0]:
            raise ValueError(
                "input_chunk_length tuple must be (min, max) with 1 <= min <= max"
            )
        return value

    @model_validator(mode="after")
    def validate_campaign(self) -> FoundationCampaignConfig:
        names = [item.public_name for item in self.models]
        if not names or len(names) != len(set(names)):
            raise ValueError(
                "foundation model identities must be non-empty and unique"
            )
        input_max = (
            self.input_chunk_length
            if isinstance(self.input_chunk_length, int)
            else self.input_chunk_length[1]
        )
        for item in self.models:
            enabled = bool(item.finetuning)
            if self.track == "zero_shot" and enabled:
                raise ValueError("zero_shot track requires finetuning=False")
            if self.track == "fine_tune" and not enabled:
                raise ValueError(
                    "fine_tune track requires finetuning=True or partial config"
                )
            capability = FOUNDATION_CAPABILITIES[item.public_name]
            if (
                capability.max_input_chunk_length is not None
                and input_max > capability.max_input_chunk_length
            ):
                raise ValueError(
                    f"{item.public_name} input_chunk_length exceeds "
                    f"{capability.max_input_chunk_length}"
                )
            total = self.output_chunk_length + self.output_chunk_shift
            if (
                capability.max_output_plus_shift is not None
                and total > capability.max_output_plus_shift
            ):
                raise ValueError(
                    f"{item.public_name} output plus shift exceeds "
                    f"{capability.max_output_plus_shift}"
                )
        if self.output_chunk_shift and self.horizon > self.output_chunk_length:
            raise ValueError("output_chunk_shift prohibits autoregressive horizon")
        if self.predict_likelihood_parameters and self.num_samples != 1:
            raise ValueError(
                "likelihood parameter prediction requires num_samples=1"
            )
        return self


class FoundationSourceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_kind: Literal["local", "hub_cache", "hub_download"]
    resolved_revision: str = Field(min_length=1)
    local_dir_exists: bool
    local_manifest_sha256: str | None = None
    files_count: int = Field(default=0, ge=0)
    total_bytes: int = Field(default=0, ge=0)
    download_performed: bool = False
    cache_hit: bool = False


class FoundationTrackObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enable_finetuning_effective: bool
    optimizer_steps: int = Field(ge=0)
    parameters_changed: bool


@dataclass(frozen=True)
class FoundationModelResult:
    model_name: str
    status: str
    predictions: tuple[tuple[float, ...], ...] | None
    failure_class: str | None
    message: str | None
    argument_ledger: tuple[dict[str, Any], ...]
    capability_certification: dict[str, Any] | None
    source_certification: dict[str, Any] | None
    track_certification: dict[str, Any] | None
    device_certifications: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]


SourceProbe = Callable[
    [FoundationModelConfig, Any | None],
    FoundationSourceObservation,
]
TrackProbe = Callable[[str, Any], FoundationTrackObservation]
DeviceProbe = Callable[[str, Any, Any, int | None], TorchRuntimeObservation]


class FoundationCertificationError(RuntimeError):
    def __init__(self, record: dict[str, Any]) -> None:
        self.record = record
        super().__init__(f"{record['failure_class']}: {record['message']}")


def canonical_capability_payload() -> dict[str, Any]:
    return {
        name: FOUNDATION_CAPABILITIES[name].model_dump(mode="json")
        for name in FOUNDATION_MODEL_IDENTITIES
    }


def capability_matrix_sha256() -> str:
    encoded = json.dumps(
        canonical_capability_payload(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def certify_source(
    config: FoundationSourceConfig,
    observation: FoundationSourceObservation,
) -> dict[str, Any]:
    evidence = observation.model_dump(mode="json")
    failure: tuple[str, str] | None = None
    if not config.revision_is_resolved:
        failure = (
            "FOUNDATION_REVISION_UNRESOLVED",
            "model revision is not pinned",
        )
    elif observation.resolved_revision != config.hub_model_revision:
        failure = (
            "FOUNDATION_REVISION_MISMATCH",
            "resolved revision differs from request",
        )
    elif not config.allow_remote_download and observation.download_performed:
        failure = (
            "REMOTE_DOWNLOAD_REJECTED",
            "offline contract observed a download",
        )
    elif observation.source_kind == "local":
        digest = observation.local_manifest_sha256 or ""
        if not observation.local_dir_exists:
            failure = (
                "FOUNDATION_ARTIFACT_MISSING",
                "local model directory does not exist",
            )
        elif len(digest) != 64 or any(
            item not in "0123456789abcdef" for item in digest
        ):
            failure = (
                "FOUNDATION_ARTIFACT_UNVERIFIED",
                "local manifest SHA-256 is missing",
            )
        elif observation.files_count < 1 or observation.total_bytes < 1:
            failure = (
                "FOUNDATION_ARTIFACT_EMPTY",
                "local model artifact is empty",
            )
    elif observation.source_kind == "hub_download":
        if not config.allow_remote_download:
            failure = (
                "REMOTE_DOWNLOAD_REJECTED",
                "remote download is disabled",
            )
    elif observation.source_kind == "hub_cache" and not observation.cache_hit:
        failure = (
            "FOUNDATION_CACHE_EVIDENCE_MISSING",
            "hub cache hit was not proven",
        )
    return {
        "passed": failure is None,
        "failure_class": None if failure is None else failure[0],
        "message": None if failure is None else failure[1],
        "evidence": evidence,
    }


def _runtime_capability_value(model: Any, name: str) -> bool | None:
    if not hasattr(model, name):
        return None
    value = getattr(model, name)
    if callable(value):
        try:
            value = value()
        except TypeError:
            return None
    return value if isinstance(value, bool) else None


def certify_capabilities(
    model_name: str,
    model: Any,
    *,
    use_past_covariates: bool,
    use_future_covariates: bool,
    series_layout: str,
) -> dict[str, Any]:
    expected = FOUNDATION_CAPABILITIES[model_name]
    names = (
        "supports_past_covariates",
        "supports_future_covariates",
        "supports_multivariate",
        "supports_probabilistic_prediction",
    )
    runtime = {
        name: _runtime_capability_value(model, name)
        for name in names
    }
    drift = {
        name: {
            "expected": getattr(expected, name),
            "runtime": runtime[name],
        }
        for name in names
        if runtime[name] is None
        or runtime[name] != getattr(expected, name)
    }
    failure: tuple[str, str] | None = None
    if drift:
        failure = (
            "CAPABILITY_DRIFT",
            f"runtime capability mismatch: {sorted(drift)}",
        )
    elif use_past_covariates and not expected.supports_past_covariates:
        failure = (
            "COVARIATE_UNSUPPORTED",
            "past covariates are not supported",
        )
    elif use_future_covariates and not expected.supports_future_covariates:
        failure = (
            "COVARIATE_UNSUPPORTED",
            "future covariates are not supported",
        )
    elif (
        series_layout == "position_multivariate"
        and not expected.supports_multivariate
    ):
        failure = (
            "MULTIVARIATE_UNSUPPORTED",
            "multivariate input is not supported",
        )
    return {
        "passed": failure is None,
        "failure_class": None if failure is None else failure[0],
        "message": None if failure is None else failure[1],
        "expected": expected.model_dump(mode="json"),
        "runtime": runtime,
        "drift": drift,
    }


def certify_track(
    track: str,
    observation: FoundationTrackObservation,
) -> dict[str, Any]:
    failure: tuple[str, str] | None = None
    if track == "zero_shot":
        if observation.enable_finetuning_effective:
            failure = (
                "ZERO_SHOT_FINETUNING_ENABLED",
                "fine-tuning was enabled",
            )
        elif observation.optimizer_steps != 0 or observation.parameters_changed:
            failure = (
                "ZERO_SHOT_TRAINING_DETECTED",
                "zero-shot changed model parameters",
            )
    else:
        if not observation.enable_finetuning_effective:
            failure = (
                "FINETUNING_NOT_ENABLED",
                "fine-tuning flag was not effective",
            )
        elif observation.optimizer_steps < 1:
            failure = (
                "FINETUNING_NO_OPTIMIZER_STEP",
                "no optimizer step was observed",
            )
        elif not observation.parameters_changed:
            failure = (
                "FINETUNING_PARAMETERS_UNCHANGED",
                "parameters did not change",
            )
    return {
        "passed": failure is None,
        "failure_class": None if failure is None else failure[0],
        "message": None if failure is None else failure[1],
        "evidence": observation.model_dump(mode="json"),
    }


def _constructor_args(
    campaign: FoundationCampaignConfig,
    model: FoundationModelConfig,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "input_chunk_length": campaign.input_chunk_length,
        "output_chunk_length": campaign.output_chunk_length,
        "output_chunk_shift": campaign.output_chunk_shift,
        "hub_model_name": model.source.hub_model_name,
        "hub_model_revision": model.source.hub_model_revision,
        "local_dir": model.source.local_dir,
        "enable_finetuning": model.finetuning,
        "pl_trainer_kwargs": campaign.device.trainer_kwargs(),
        **model.model_args,
    }
    if FOUNDATION_CAPABILITIES[
        model.public_name
    ].requires_license_acceptance:
        payload["accept_license"] = model.accept_license
    return payload


def _array(prediction: Any) -> np.ndarray:
    values = prediction.values() if hasattr(prediction, "values") else prediction
    array = np.asarray(values, dtype=float)
    if not np.isfinite(array).all():
        raise ValueError("prediction contains NaN or Inf")
    return array


def _normalize_single(
    prediction: Any,
    positions: int,
    horizon: int,
) -> tuple[tuple[float, ...], ...]:
    array = _array(prediction)
    if array.ndim == 1:
        if positions != 1 or array.size != horizon:
            raise ValueError("prediction shape mismatch")
        return (tuple(float(item) for item in array),)
    if array.ndim >= 3:
        array = np.median(array, axis=tuple(range(2, array.ndim)))
    if array.shape == (horizon, positions):
        array = array.T
    if array.shape != (positions, horizon):
        raise ValueError("prediction shape mismatch")
    return tuple(tuple(float(item) for item in row) for row in array)


def _normalize_sequence(
    predictions: Any,
    positions: int,
    horizon: int,
) -> tuple[tuple[float, ...], ...]:
    blocks = (
        list(predictions)
        if isinstance(predictions, (list, tuple))
        else [predictions]
    )
    if len(blocks) != positions:
        raise ValueError("prediction position count mismatch")
    rows: list[tuple[float, ...]] = []
    for block in blocks:
        array = _array(block).reshape(-1)
        if array.size != horizon:
            raise ValueError("prediction horizon mismatch")
        rows.append(tuple(float(item) for item in array))
    return tuple(rows)


def _ledger(items: list[Any]) -> tuple[dict[str, Any], ...]:
    return tuple(item.model_dump(mode="json") for item in items)


def _prepare_series(
    config: FoundationCampaignConfig,
    frame: pd.DataFrame,
    geometry: GameGeometry,
    timeseries_cls: Any | None,
) -> tuple[Any, int]:
    if config.series_layout == "position_multivariate":
        payload = build_position_multivariate(frame, geometry)
        return to_darts_multivariate(payload, timeseries_cls), geometry.positions
    payload = build_position_local(frame, geometry)
    return to_darts_local(payload, timeseries_cls), geometry.positions


def _fit_predict(
    model: Any,
    config: FoundationCampaignConfig,
    series: Any,
    past_covariates: Any,
    future_covariates: Any,
) -> tuple[Any, tuple[dict[str, Any], ...]]:
    ledgers: list[Any] = []
    fit_request: dict[str, Any] = {"series": series, **config.fit_args}
    if config.use_past_covariates:
        fit_request["past_covariates"] = past_covariates
    if config.use_future_covariates:
        fit_request["future_covariates"] = future_covariates
    effective, current = classify_arguments(model.fit, fit_request)
    ledgers.extend(current)
    model.fit(**effective)

    predict_request: dict[str, Any] = {
        "n": config.horizon,
        "series": series,
        "num_samples": config.num_samples,
        "predict_likelihood_parameters": config.predict_likelihood_parameters,
        **config.predict_args,
    }
    if config.use_past_covariates:
        predict_request["past_covariates"] = past_covariates
    if config.use_future_covariates:
        predict_request["future_covariates"] = future_covariates
    effective, current = classify_arguments(model.predict, predict_request)
    ledgers.extend(current)
    return model.predict(**effective), _ledger(ledgers)


def _failed_result(
    item: FoundationModelConfig,
    config: FoundationCampaignConfig,
    failure_class: str,
    message: str,
    *,
    ledger: tuple[dict[str, Any], ...] = (),
    capability: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
    track: dict[str, Any] | None = None,
    devices: tuple[dict[str, Any], ...] = (),
) -> FoundationModelResult:
    return FoundationModelResult(
        model_name=item.public_name,
        status="FAILED",
        predictions=None,
        failure_class=failure_class,
        message=message,
        argument_ledger=ledger,
        capability_certification=capability,
        source_certification=source,
        track_certification=track,
        device_certifications=devices,
        metadata={"track": config.track},
    )


def run_foundation_matrix(
    config: FoundationCampaignConfig,
    frame: pd.DataFrame,
    geometry: GameGeometry,
    *,
    past_covariates: Any = None,
    future_covariates: Any = None,
    models_module: Any | None = None,
    timeseries_cls: Any | None = None,
    source_probe: SourceProbe,
    track_probe: TrackProbe,
    device_probe: DeviceProbe,
) -> tuple[FoundationModelResult, ...]:
    source_frame = frame.copy(deep=True)
    if config.use_past_covariates and past_covariates is None:
        raise ValueError("past_covariates are required by the campaign")
    if config.use_future_covariates and future_covariates is None:
        raise ValueError("future_covariates are required by the campaign")
    series, positions = _prepare_series(
        config,
        frame,
        geometry,
        timeseries_cls,
    )
    try:
        module = models_module or importlib.import_module("darts.models")
    except Exception as error:
        return tuple(
            _failed_result(
                item,
                config,
                "DEPENDENCY_MISSING",
                str(error),
            )
            for item in config.models
        )

    results: list[FoundationModelResult] = []
    for item in config.models:
        ledger: tuple[dict[str, Any], ...] = ()
        source_record: dict[str, Any] | None = None
        capability_record: dict[str, Any] | None = None
        track_record: dict[str, Any] | None = None
        device_records: list[dict[str, Any]] = []
        try:
            if not item.source.revision_is_resolved:
                raise FoundationCertificationError({
                    "failure_class": "FOUNDATION_REVISION_UNRESOLVED",
                    "message": "model revision is not pinned",
                })
            source_record = certify_source(
                item.source,
                source_probe(item, None),
            )
            if not source_record["passed"]:
                raise FoundationCertificationError(source_record)

            model_cls = getattr(module, item.public_name)
            args, constructor_ledger = classify_arguments(
                model_cls,
                _constructor_args(config, item),
            )
            ledger = _ledger(constructor_ledger)
            model = model_cls(**args)
            capability_record = certify_capabilities(
                item.public_name,
                model,
                use_past_covariates=config.use_past_covariates,
                use_future_covariates=config.use_future_covariates,
                series_layout=config.series_layout,
            )
            if not capability_record["passed"]:
                raise FoundationCertificationError(capability_record)

            if config.series_layout == "position_local":
                rows: list[tuple[float, ...]] = []
                extra_ledger: list[dict[str, Any]] = []
                for position, single_series in enumerate(series):
                    current_model = model_cls(**args)
                    prediction, current_ledger = _fit_predict(
                        current_model,
                        config,
                        single_series,
                        None
                        if past_covariates is None
                        else past_covariates[position],
                        None
                        if future_covariates is None
                        else future_covariates[position],
                    )
                    extra_ledger.extend(current_ledger)
                    rows.append(
                        _normalize_single(
                            prediction,
                            1,
                            config.horizon,
                        )[0]
                    )
                    device_record = certify_device_use(
                        config.device,
                        device_probe(
                            item.public_name,
                            current_model,
                            prediction,
                            position,
                        ),
                    )
                    device_record = {
                        "position": position,
                        **device_record,
                    }
                    device_records.append(device_record)
                    if not device_record["passed"]:
                        raise FoundationCertificationError(device_record)
                    current_track = certify_track(
                        config.track,
                        track_probe(item.public_name, current_model),
                    )
                    if not current_track["passed"]:
                        raise FoundationCertificationError(current_track)
                    track_record = current_track
                predictions = tuple(rows)
                ledger = (*ledger, *extra_ledger)
            else:
                prediction, current_ledger = _fit_predict(
                    model,
                    config,
                    series,
                    past_covariates,
                    future_covariates,
                )
                ledger = (*ledger, *current_ledger)
                if config.series_layout == "position_multivariate":
                    predictions = _normalize_single(
                        prediction,
                        positions,
                        config.horizon,
                    )
                else:
                    predictions = _normalize_sequence(
                        prediction,
                        positions,
                        config.horizon,
                    )
                device_record = certify_device_use(
                    config.device,
                    device_probe(
                        item.public_name,
                        model,
                        prediction,
                        None,
                    ),
                )
                device_records.append({
                    "position": None,
                    **device_record,
                })
                if not device_record["passed"]:
                    raise FoundationCertificationError(device_record)
                track_record = certify_track(
                    config.track,
                    track_probe(item.public_name, model),
                )
                if not track_record["passed"]:
                    raise FoundationCertificationError(track_record)

            results.append(FoundationModelResult(
                model_name=item.public_name,
                status="PASS",
                predictions=predictions,
                failure_class=None,
                message=None,
                argument_ledger=ledger,
                capability_certification=capability_record,
                source_certification=source_record,
                track_certification=track_record,
                device_certifications=tuple(device_records),
                metadata={
                    "track": config.track,
                    "hub_model_name": item.source.hub_model_name,
                    "hub_model_revision": item.source.hub_model_revision,
                    "capability_matrix_sha256": capability_matrix_sha256(),
                },
            ))
        except FoundationCertificationError as error:
            results.append(_failed_result(
                item,
                config,
                error.record["failure_class"],
                error.record["message"],
                ledger=ledger,
                capability=capability_record,
                source=source_record,
                track=track_record,
                devices=tuple(device_records),
            ))
        except AttributeError as error:
            results.append(_failed_result(
                item,
                config,
                "DEPENDENCY_MISSING",
                str(error),
                ledger=ledger,
                capability=capability_record,
                source=source_record,
                track=track_record,
                devices=tuple(device_records),
            ))
        except ValueError as error:
            results.append(_failed_result(
                item,
                config,
                "INVALID_REQUEST",
                str(error),
                ledger=ledger,
                capability=capability_record,
                source=source_record,
                track=track_record,
                devices=tuple(device_records),
            ))
        except Exception as error:
            results.append(_failed_result(
                item,
                config,
                "RUNTIME_FAILED",
                str(error),
                ledger=ledger,
                capability=capability_record,
                source=source_record,
                track=track_record,
                devices=tuple(device_records),
            ))
    if not frame.equals(source_frame):
        raise RuntimeError("raw frame was mutated")
    return tuple(results)

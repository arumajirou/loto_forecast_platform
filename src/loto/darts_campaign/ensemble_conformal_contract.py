from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

P10_MODEL_IDENTITIES = ('NaiveEnsembleModel', 'RegressionEnsembleModel', 'ConformalNaiveModel',
    'ConformalQRModel')

class P10ContractError(ValueError):
    """Base exception for fail-closed P10 contract failures."""

class DependencyUnavailableError(P10ContractError):
    """Raised when a requested component cannot be loaded."""

class CertificationError(P10ContractError):
    """Raised when runtime evidence does not satisfy a contract."""

class TemporalPartition(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    train_start: int = Field(default=0, ge=0)
    train_end: int = Field(ge=1)
    calibration_start: int = Field(ge=1)
    calibration_end: int = Field(ge=2)
    evaluation_start: int = Field(ge=2)
    evaluation_end: int = Field(ge=3)

    @model_validator(mode='after')
    def validate_order(self) -> TemporalPartition:
        ordered = (
            self.train_start
            < self.train_end
            <= self.calibration_start
            < self.calibration_end
            <= self.evaluation_start
            < self.evaluation_end
        )
        if not ordered:
            raise ValueError(
                'Train, calibration, and evaluation must be ordered '
                'and non-overlapping'
            )
        return self

class BaseModelEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    model_id: str = Field(min_length=1)
    model_family: Literal['local', 'regression', 'torch', 'foundation', 'ensemble']
    available: bool = True
    failure_class: str | None = None
    failure_message: str | None = None
    is_global: bool = False
    is_fitted: bool = False
    supports_probabilistic_prediction: bool = False
    supports_likelihood_parameters: bool = False
    output_chunk_shift: int = Field(default=0, ge=0)
    output_chunk_length: int | None = Field(default=None, ge=1)
    likelihood_id: str | None = None
    quantiles: tuple[float, ...] = ()

    @model_validator(mode='after')
    def validate_availability(self) -> BaseModelEvidence:
        if self.available and (self.failure_class or self.failure_message):
            raise ValueError('available models cannot carry failure evidence')
        if not self.available and (not self.failure_class):
            raise ValueError('unavailable models require failure_class')
        if self.quantiles:
            _validate_quantiles(self.quantiles)
        return self

class EnsembleConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    public_name: Literal['NaiveEnsembleModel', 'RegressionEnsembleModel']
    base_model_ids: tuple[str, ...]
    train_forecasting_models: bool = True
    train_using_historical_forecasts: bool = False
    regression_train_n_points: int = 20
    regression_train_num_samples: int = Field(default=1, ge=1)
    regression_train_samples_reduction: str | float | None = 'median'
    regression_model_id: str | None = None
    num_samples: int = Field(default=1, ge=1)
    predict_likelihood_parameters: bool = False
    constructor_args: dict[str, Any] = Field(default_factory=dict)
    fit_args: dict[str, Any] = Field(default_factory=dict)
    predict_args: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_config(self) -> EnsembleConfig:
        if len(self.base_model_ids) < 2:
            raise ValueError('ensemble requires at least two base models')
        if len(set(self.base_model_ids)) != len(self.base_model_ids):
            raise ValueError('base_model_ids must be unique')
        if self.public_name == 'NaiveEnsembleModel':
            regression_only = {
                'train_using_historical_forecasts': (
                    self.train_using_historical_forecasts
                ),
                'regression_model_id': self.regression_model_id,
            }
            if any((value for value in regression_only.values())):
                raise ValueError('naive ensemble cannot use regression-only settings')
        else:
            if self.regression_train_n_points == 0 or self.regression_train_n_points < -1:
                raise ValueError('regression_train_n_points must be -1 or positive')
            reduction = self.regression_train_samples_reduction
            if isinstance(reduction, str) and reduction not in {'mean', 'median'}:
                raise ValueError('unsupported regression sample reduction')
            if isinstance(reduction, float) and (not 0.0 <= reduction <= 1.0):
                raise ValueError('quantile sample reduction must be in [0, 1]')
        _validate_protected_args(self.constructor_args, {'forecasting_models',
            'train_forecasting_models', 'regression_train_n_points', 'regression_model',
            'regression_train_num_samples', 'regression_train_samples_reduction',
            'train_using_historical_forecasts'}, 'constructor')
        _validate_protected_args(self.fit_args, {'series'}, 'fit')
        _validate_protected_args(self.predict_args, {'n', 'series', 'num_samples',
            'predict_likelihood_parameters'}, 'predict')
        return self

class ConformalConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    public_name: Literal['ConformalNaiveModel', 'ConformalQRModel']
    base_model_id: str = Field(min_length=1)
    quantiles: tuple[float, ...]
    symmetric: bool = True
    cal_length: int | None = Field(default=None, ge=1)
    cal_stride: int = Field(default=1, ge=1)
    cal_num_samples: int = Field(default=500, ge=1)
    random_state: int = 1
    num_samples: int = Field(default=1, ge=1)
    predict_likelihood_parameters: bool = True
    require_median_base_parity: bool = True
    constructor_args: dict[str, Any] = Field(default_factory=dict)
    predict_args: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_config(self) -> ConformalConfig:
        _validate_quantiles(self.quantiles)
        if self.predict_likelihood_parameters and self.num_samples != 1:
            raise ValueError('likelihood-parameter prediction requires num_samples equal to one')
        _validate_protected_args(self.constructor_args, {'model', 'quantiles',
            'symmetric', 'cal_length', 'cal_stride', 'cal_num_samples', 'random_state'},
            'constructor')
        _validate_protected_args(self.predict_args, {'n', 'series', 'num_samples',
            'predict_likelihood_parameters'}, 'predict')
        return self

class P10CampaignConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal[1] = 1
    partition: TemporalPartition
    ensembles: tuple[EnsembleConfig, ...]
    conformal_models: tuple[ConformalConfig, ...]
    seeds: tuple[int, ...] = (1, 7, 19)
    fold_ids: tuple[int, ...] = (0,)
    outer_workers: int = Field(default=8, ge=1)
    max_gpu_jobs: int = Field(default=1, ge=1)
    point_tolerance: float = Field(default=1e-12, ge=0.0)
    interval_tolerance: float = Field(default=1e-12, ge=0.0)

    @model_validator(mode='after')
    def validate_campaign(self) -> P10CampaignConfig:
        requested = tuple((item.public_name for item in self.ensembles)) \
            + tuple((item.public_name for item in self.conformal_models))
        if set(requested) != set(P10_MODEL_IDENTITIES):
            raise ValueError('P10 campaign must retain all four required identities')
        if len(requested) != len(P10_MODEL_IDENTITIES):
            raise ValueError('P10 model identities must appear exactly once')
        if len(self.seeds) < 2 or len(set(self.seeds)) != len(self.seeds):
            raise ValueError('P10 requires at least two unique seeds')
        if not self.fold_ids or len(set(self.fold_ids)) != len(self.fold_ids):
            raise ValueError('fold_ids must be non-empty and unique')
        if self.max_gpu_jobs != 1:
            raise ValueError('P10 keeps GPU model execution serialized')
        return self

class ArgumentLedgerEntry(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    target: str
    phase: Literal['constructor', 'fit', 'predict']
    argument: str
    status: Literal['accepted', 'rejected']
    reason: str
    value_repr: str

class EnsemblePlan(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    public_name: str
    base_model_ids: tuple[str, ...]
    output_chunk_shift: int
    all_global: bool
    all_prefitted: bool
    probabilistic_base_ids: tuple[str, ...]
    effective_regression_train_n_points: int | None
    effective_train_num_samples: int
    argument_ledger: tuple[ArgumentLedgerEntry, ...] = ()

def _validate_protected_args(arguments: Mapping[str, Any], protected: set[str], phase: str) -> None:
    overlap = sorted(set(arguments) & protected)
    if overlap:
        raise ValueError(f'{phase} extra arguments override protected fields: {overlap}')

def _validate_quantiles(quantiles: Sequence[float]) -> None:
    values = tuple((float(item) for item in quantiles))
    if len(values) < 3 or len(values) % 2 == 0:
        raise ValueError('quantiles must contain an odd number of at least three values')
    if values != tuple(sorted(values)) or len(set(values)) != len(values):
        raise ValueError('quantiles must be strictly increasing and unique')
    if any((value <= 0.0 or value >= 1.0 for value in values)):
        raise ValueError('quantiles must lie strictly between zero and one')
    if 0.5 not in values or values[len(values) // 2] != 0.5:
        raise ValueError('quantiles must be centered on the median')
    for lower, upper in zip(values[:len(values) // 2], reversed(values[len(values) // 2 + 1:])):
        if not np.isclose(lower + upper, 1.0, atol=1e-12, rtol=0.0):
            raise ValueError('quantiles must define symmetric coverage pairs')

def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
        default=str).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()

def p10_identity_sha256() -> str:
    return canonical_sha256(P10_MODEL_IDENTITIES)

def classify_arguments(target: Callable[..., Any], requested: Mapping[str, Any], *,
    target_name: str, phase: Literal['constructor', 'fit', 'predict']) -> tuple[dict[str, Any],
    tuple[ArgumentLedgerEntry, ...]]:
    signature = inspect.signature(target)
    accepts_kwargs = any((parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()))
    accepted_names = set(signature.parameters)
    effective: dict[str, Any] = {}
    ledger: list[ArgumentLedgerEntry] = []
    rejected: list[str] = []
    for key, value in requested.items():
        accepted = key in accepted_names or accepts_kwargs
        ledger.append(ArgumentLedgerEntry(target=target_name, phase=phase, argument=key,
            status='accepted' if accepted else 'rejected',
            reason='callable signature accepts argument' if accepted
            else 'argument absent from callable signature', value_repr=repr(value)))
        if accepted:
            effective[key] = value
        else:
            rejected.append(key)
    if rejected:
        raise P10ContractError(f'rejected {phase} arguments for {target_name}: {sorted(rejected)}')
    return (effective, tuple(ledger))

def build_ensemble_plan(config: EnsembleConfig, evidence: Mapping[str, BaseModelEvidence], *,
    constructor: Callable[..., Any] | None=None, fit_method: Callable[..., Any] | None=None,
    predict_method: Callable[..., Any] | None=None) -> EnsemblePlan:
    missing = [model_id for model_id in config.base_model_ids if model_id not in evidence]
    if missing:
        raise DependencyUnavailableError(f'missing base model evidence: {missing}')
    models = [evidence[model_id] for model_id in config.base_model_ids]
    unavailable = [model for model in models if not model.available]
    if unavailable:
        details = [(model.model_id, model.failure_class) for model in unavailable]
        raise DependencyUnavailableError(f'unavailable base models: {details}')
    shifts = {model.output_chunk_shift for model in models}
    if len(shifts) != 1:
        raise P10ContractError('all base models must share output_chunk_shift')
    all_global = all((model.is_global for model in models))
    all_prefitted = all((model.is_fitted for model in models))
    if not config.train_forecasting_models and (not (all_global and all_prefitted)):
        raise P10ContractError('disabled base-model training requires pre-fitted global models')
    effective_train_points: int | None = None
    if config.public_name == 'RegressionEnsembleModel':
        if config.train_using_historical_forecasts and (not all_global):
            raise P10ContractError(
                'historical-forecast stacking requires exclusively global base models'
            )
        if config.regression_train_n_points == -1:
            if config.train_forecasting_models or not (all_global and all_prefitted):
                raise P10ContractError(
                    'regression_train_n_points=-1 requires pre-fitted global models '
                    'and train_forecasting_models=False'
                )
        effective_train_points = config.regression_train_n_points
    if config.predict_likelihood_parameters:
        if not all((model.supports_likelihood_parameters for model in models)):
            raise P10ContractError(
                'likelihood-parameter ensembling requires support from every base model'
            )
        likelihoods = {model.likelihood_id for model in models}
        quantiles = {model.quantiles for model in models}
        if len(likelihoods) != 1 or None in likelihoods or len(quantiles) != 1:
            raise P10ContractError(
                'likelihood-parameter ensembling requires identical likelihoods '
                'and quantiles'
            )
    ledger: list[ArgumentLedgerEntry] = []
    if constructor is not None:
        _, decisions = classify_arguments(constructor, config.constructor_args,
            target_name=config.public_name, phase='constructor')
        ledger.extend(decisions)
    if fit_method is not None:
        _, decisions = classify_arguments(fit_method, config.fit_args,
            target_name=config.public_name, phase='fit')
        ledger.extend(decisions)
    if predict_method is not None:
        _, decisions = classify_arguments(predict_method, config.predict_args,
            target_name=config.public_name, phase='predict')
        ledger.extend(decisions)
    effective_samples = config.regression_train_num_samples
    return EnsemblePlan(public_name=config.public_name, base_model_ids=config.base_model_ids,
        output_chunk_shift=next(iter(shifts)), all_global=all_global,
        all_prefitted=all_prefitted, probabilistic_base_ids=tuple((model.model_id
        for model in models if model.supports_probabilistic_prediction)),
        effective_regression_train_n_points=effective_train_points,
        effective_train_num_samples=effective_samples, argument_ledger=tuple(ledger))

def validate_conformal_base(config: ConformalConfig, evidence: Mapping[str, BaseModelEvidence],
    partition: TemporalPartition) -> BaseModelEvidence:
    model = evidence.get(config.base_model_id)
    if model is None:
        raise DependencyUnavailableError(f'missing conformal base model: {config.base_model_id}')
    if not model.available:
        raise DependencyUnavailableError(f'conformal base model unavailable: {model.failure_class}')
    if not model.is_global or not model.is_fitted:
        raise P10ContractError('conformal models require a pre-trained global forecasting model')
    if config.public_name == 'ConformalQRModel':
        if not model.supports_probabilistic_prediction:
            raise P10ContractError('ConformalQRModel requires a probabilistic base model')
        if model.quantiles and (not set(config.quantiles).issubset(model.quantiles)):
            raise P10ContractError(
                'ConformalQRModel requested quantiles are absent from base-model '
                'evidence'
            )
    calibration_rows = tuple(range(partition.calibration_start, partition.calibration_end,
        config.cal_stride))
    if not calibration_rows:
        raise P10ContractError('calibration window produces no scores')
    if config.cal_length is not None and len(calibration_rows) < config.cal_length:
        raise P10ContractError(
            'calibration window is shorter than requested cal_length after striding'
        )
    return model

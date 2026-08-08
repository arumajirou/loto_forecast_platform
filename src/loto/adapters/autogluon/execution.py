from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from .contracts import (
    ArgumentLedgerEntry,
    ArgumentStatus,
    ExecutionMode,
    ProviderRequestV2,
)
from .inventory import SOURCE_MODEL_SPECS


class ExecutionPlanError(ValueError):
    def __init__(self, code: str, argument: str, message: str):
        super().__init__(message)
        self.code = code
        self.argument = argument


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    execution_mode: str
    selected_model_ids: tuple[str, ...]
    predictor_kwargs: dict[str, Any]
    fit_kwargs: dict[str, Any]
    argument_ledger: tuple[ArgumentLedgerEntry, ...]
    plan_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["argument_ledger"] = [
            entry.model_dump(mode="json") for entry in self.argument_ledger
        ]
        return payload


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _ledger(
    argument: str,
    requested_value: Any,
    effective_value: Any,
    status: ArgumentStatus,
    reason: str | None = None,
) -> ArgumentLedgerEntry:
    return ArgumentLedgerEntry(
        argument=argument,
        requested_value=requested_value,
        effective_value=effective_value,
        status=status,
        reason=reason,
    )


def _validate_model_ids(model_ids: tuple[str, ...]) -> None:
    known = {spec.alias for spec in SOURCE_MODEL_SPECS}
    unknown = sorted(set(model_ids) - known)
    if unknown:
        raise ExecutionPlanError(
            "UNKNOWN_MODEL_ID",
            "model_ids",
            f"model_ids are not declared by AutoGluon 1.5.0 source manifest: {unknown}",
        )


def _explicit_hyperparameters(request: ProviderRequestV2) -> dict[str, dict[str, Any]]:
    model_ids = request.model_ids
    requested = request.fit.hyperparameters
    if requested is None:
        return {model_id: {} for model_id in model_ids}
    if isinstance(requested, str):
        raise ExecutionPlanError(
            "EXPLICIT_HYPERPARAMETERS_STRING_UNSUPPORTED",
            "fit.hyperparameters",
            "explicit model modes require a dictionary, not a preset string",
        )

    known = {spec.alias for spec in SOURCE_MODEL_SPECS}
    alias_keys = set(requested) & known
    if alias_keys:
        unexpected = sorted(set(requested) - set(model_ids))
        if unexpected:
            raise ExecutionPlanError(
                "HYPERPARAMETER_MODEL_MISMATCH",
                "fit.hyperparameters",
                f"hyperparameter model keys are not selected model_ids: {unexpected}",
            )
        resolved: dict[str, dict[str, Any]] = {}
        for model_id in model_ids:
            config = requested.get(model_id, {})
            if not isinstance(config, dict):
                raise ExecutionPlanError(
                    "MODEL_CONFIG_NOT_MAPPING",
                    f"fit.hyperparameters.{model_id}",
                    f"configuration for {model_id!r} must be a dictionary",
                )
            resolved[model_id] = dict(config)
        return resolved

    if len(model_ids) != 1:
        raise ExecutionPlanError(
            "MULTI_MODEL_CONFIG_REQUIRES_MODEL_KEYS",
            "fit.hyperparameters",
            "explicit_multi_model configuration must be keyed by selected model_ids",
        )
    return {model_ids[0]: dict(requested)}


def _validate_fit_mode(request: ProviderRequestV2) -> None:
    fit = request.fit
    explicit_mode = request.execution_mode in {
        ExecutionMode.EXPLICIT_SINGLE_MODEL,
        ExecutionMode.EXPLICIT_MULTI_MODEL,
        ExecutionMode.HPO_SINGLE_MODEL,
    }
    hpo_mode = request.execution_mode is ExecutionMode.HPO_SINGLE_MODEL

    if fit.hyperparameter_tune_kwargs is not None and not hpo_mode:
        raise ExecutionPlanError(
            "HPO_ARGUMENT_WITHOUT_HPO_MODE",
            "fit.hyperparameter_tune_kwargs",
            "hyperparameter_tune_kwargs requires hpo_single_model execution mode",
        )
    if hpo_mode and fit.hyperparameter_tune_kwargs is None:
        raise ExecutionPlanError(
            "HPO_CONFIGURATION_REQUIRED",
            "fit.hyperparameter_tune_kwargs",
            "hpo_single_model requires hyperparameter_tune_kwargs",
        )
    if explicit_mode and fit.excluded_model_types:
        raise ExecutionPlanError(
            "EXCLUDED_MODELS_CONFLICT_WITH_EXPLICIT_MODE",
            "fit.excluded_model_types",
            "excluded_model_types cannot be combined with explicit model selection",
        )
    if request.execution_mode is ExecutionMode.PRESET_AUTOML and isinstance(
        fit.hyperparameters, dict
    ):
        raise ExecutionPlanError(
            "PRESET_MODE_EXPLICIT_HYPERPARAMETERS",
            "fit.hyperparameters",
            "dictionary hyperparameters require an explicit model execution mode",
        )
    single_mode = request.execution_mode in {
        ExecutionMode.EXPLICIT_SINGLE_MODEL,
        ExecutionMode.HPO_SINGLE_MODEL,
    }
    if single_mode and fit.ensemble_hyperparameters is not None:
        raise ExecutionPlanError(
            "ENSEMBLE_CONFIG_CONFLICT_WITH_SINGLE_MODEL",
            "fit.ensemble_hyperparameters",
            "single-model execution cannot accept ensemble_hyperparameters",
        )
    if not fit.enable_ensemble and fit.ensemble_hyperparameters is not None:
        raise ExecutionPlanError(
            "ENSEMBLE_CONFIG_WHILE_DISABLED",
            "fit.ensemble_hyperparameters",
            "ensemble_hyperparameters requires enable_ensemble=true",
        )


def build_execution_plan(request: ProviderRequestV2) -> ExecutionPlan:
    if request.execution_mode in {
        ExecutionMode.ZERO_SHOT_FOUNDATION,
        ExecutionMode.FINE_TUNE_FOUNDATION,
    }:
        raise ExecutionPlanError(
            "EXECUTION_MODE_NOT_IMPLEMENTED_P4",
            "execution_mode",
            f"{request.execution_mode.value} is deferred to the foundation-model phase",
        )

    _validate_model_ids(request.model_ids)
    _validate_fit_mode(request)
    explicit_mode = request.execution_mode in {
        ExecutionMode.EXPLICIT_SINGLE_MODEL,
        ExecutionMode.EXPLICIT_MULTI_MODEL,
        ExecutionMode.HPO_SINGLE_MODEL,
    }
    hpo_mode = request.execution_mode is ExecutionMode.HPO_SINGLE_MODEL

    ledger: list[ArgumentLedgerEntry] = [
        _ledger(
            "execution_mode",
            request.execution_mode.value,
            request.execution_mode.value,
            ArgumentStatus.ACCEPTED,
        ),
        _ledger(
            "model_ids",
            request.model_ids,
            request.model_ids,
            ArgumentStatus.ACCEPTED if request.model_ids else ArgumentStatus.NOT_APPLICABLE,
        ),
    ]
    predictor = request.predictor
    predictor_kwargs: dict[str, Any] = {
        "target": predictor.target,
        "prediction_length": predictor.prediction_length,
        "freq": predictor.freq,
        "eval_metric": predictor.eval_metric,
        "quantile_levels": list(predictor.quantile_levels),
        "cache_predictions": predictor.cache_predictions,
        "path": request.artifact_dir,
        "verbosity": 0,
    }
    for name in (
        "target",
        "prediction_length",
        "freq",
        "eval_metric",
        "quantile_levels",
        "cache_predictions",
    ):
        ledger.append(
            _ledger(
                f"predictor.{name}",
                getattr(predictor, name),
                predictor_kwargs[name],
                ArgumentStatus.ACCEPTED,
            )
        )

    if predictor.known_covariates_names:
        predictor_kwargs["known_covariates_names"] = list(predictor.known_covariates_names)
        ledger.append(
            _ledger(
                "predictor.known_covariates_names",
                predictor.known_covariates_names,
                predictor_kwargs["known_covariates_names"],
                ArgumentStatus.SUPPORTED_WITH_CONDITION,
                "future known-covariate values must be supplied at predict time",
            )
        )
    else:
        ledger.append(
            _ledger(
                "predictor.known_covariates_names",
                (),
                None,
                ArgumentStatus.NOT_APPLICABLE,
            )
        )
    if predictor.eval_metric_seasonal_period is not None:
        predictor_kwargs["eval_metric_seasonal_period"] = predictor.eval_metric_seasonal_period
    ledger.append(
        _ledger(
            "predictor.eval_metric_seasonal_period",
            predictor.eval_metric_seasonal_period,
            predictor_kwargs.get("eval_metric_seasonal_period"),
            ArgumentStatus.ACCEPTED
            if predictor.eval_metric_seasonal_period is not None
            else ArgumentStatus.NOT_APPLICABLE,
        )
    )
    if predictor.horizon_weight is not None:
        predictor_kwargs["horizon_weight"] = list(predictor.horizon_weight)
        ledger.append(
            _ledger(
                "predictor.horizon_weight",
                predictor.horizon_weight,
                predictor_kwargs["horizon_weight"],
                ArgumentStatus.TRANSFORMED,
                "tuple serialized to list for the isolated provider boundary",
            )
        )
    else:
        ledger.append(
            _ledger(
                "predictor.horizon_weight",
                None,
                None,
                ArgumentStatus.NOT_APPLICABLE,
            )
        )

    fit = request.fit
    fit_kwargs: dict[str, Any] = {
        "num_val_windows": fit.num_val_windows,
        "refit_full": fit.refit_full,
        "enable_ensemble": fit.enable_ensemble,
        "skip_model_selection": fit.skip_model_selection,
        "random_seed": request.seed,
    }
    if fit.time_limit_seconds is not None:
        fit_kwargs["time_limit"] = fit.time_limit_seconds
    if fit.val_step_size is not None:
        fit_kwargs["val_step_size"] = fit.val_step_size
    if fit.refit_every_n_windows is not None:
        fit_kwargs["refit_every_n_windows"] = fit.refit_every_n_windows
    if fit.ensemble_hyperparameters is not None:
        fit_kwargs["ensemble_hyperparameters"] = fit.ensemble_hyperparameters

    if explicit_mode:
        hyperparameters = _explicit_hyperparameters(request)
        fit_kwargs["hyperparameters"] = hyperparameters
        ledger.append(
            _ledger(
                "fit.hyperparameters",
                fit.hyperparameters,
                hyperparameters,
                ArgumentStatus.TRANSFORMED,
                "model_ids converted to AutoGluon hyperparameters model keys",
            )
        )
        ledger.append(
            _ledger(
                "fit.presets",
                fit.presets,
                None,
                ArgumentStatus.DROPPED_WITH_REASON
                if fit.presets is not None
                else ArgumentStatus.NOT_APPLICABLE,
                "explicit modes disable presets to prevent hidden model injection"
                if fit.presets is not None
                else None,
            )
        )
        if request.execution_mode in {
            ExecutionMode.EXPLICIT_SINGLE_MODEL,
            ExecutionMode.HPO_SINGLE_MODEL,
        }:
            requested_ensemble = fit_kwargs["enable_ensemble"]
            fit_kwargs["enable_ensemble"] = False
            ledger.append(
                _ledger(
                    "fit.enable_ensemble",
                    requested_ensemble,
                    False,
                    ArgumentStatus.TRANSFORMED,
                    "single-model identity certification disables ensembles",
                )
            )
        else:
            ledger.append(
                _ledger(
                    "fit.enable_ensemble",
                    fit.enable_ensemble,
                    fit.enable_ensemble,
                    ArgumentStatus.ACCEPTED,
                )
            )
        if hpo_mode:
            fit_kwargs["hyperparameter_tune_kwargs"] = fit.hyperparameter_tune_kwargs
            ledger.append(
                _ledger(
                    "fit.hyperparameter_tune_kwargs",
                    fit.hyperparameter_tune_kwargs,
                    fit.hyperparameter_tune_kwargs,
                    ArgumentStatus.ACCEPTED,
                )
            )
        else:
            ledger.append(
                _ledger(
                    "fit.hyperparameter_tune_kwargs",
                    None,
                    None,
                    ArgumentStatus.NOT_APPLICABLE,
                )
            )
    else:
        if fit.presets is not None:
            fit_kwargs["presets"] = fit.presets
        if fit.hyperparameters is not None:
            fit_kwargs["hyperparameters"] = fit.hyperparameters
        if fit.excluded_model_types:
            fit_kwargs["excluded_model_types"] = list(fit.excluded_model_types)
        ledger.extend(
            [
                _ledger(
                    "fit.presets",
                    fit.presets,
                    fit.presets,
                    ArgumentStatus.ACCEPTED
                    if fit.presets is not None
                    else ArgumentStatus.NOT_APPLICABLE,
                ),
                _ledger(
                    "fit.hyperparameters",
                    fit.hyperparameters,
                    fit.hyperparameters,
                    ArgumentStatus.ACCEPTED
                    if fit.hyperparameters is not None
                    else ArgumentStatus.NOT_APPLICABLE,
                ),
                _ledger(
                    "fit.hyperparameter_tune_kwargs",
                    None,
                    None,
                    ArgumentStatus.NOT_APPLICABLE,
                ),
                _ledger(
                    "fit.enable_ensemble",
                    fit.enable_ensemble,
                    fit.enable_ensemble,
                    ArgumentStatus.ACCEPTED,
                ),
            ]
        )

    for name in (
        "time_limit_seconds",
        "num_val_windows",
        "val_step_size",
        "refit_every_n_windows",
        "refit_full",
        "skip_model_selection",
    ):
        requested_value = getattr(fit, name)
        effective_name = "time_limit" if name == "time_limit_seconds" else name
        ledger.append(
            _ledger(
                f"fit.{name}",
                requested_value,
                fit_kwargs.get(effective_name),
                ArgumentStatus.NOT_APPLICABLE
                if requested_value is None
                else ArgumentStatus.ACCEPTED,
            )
        )
    ledger.extend(
        [
            _ledger(
                "fit.excluded_model_types",
                fit.excluded_model_types,
                fit_kwargs.get("excluded_model_types"),
                ArgumentStatus.ACCEPTED
                if fit.excluded_model_types
                else ArgumentStatus.NOT_APPLICABLE,
            ),
            _ledger(
                "fit.ensemble_hyperparameters",
                fit.ensemble_hyperparameters,
                fit_kwargs.get("ensemble_hyperparameters"),
                ArgumentStatus.ACCEPTED
                if fit.ensemble_hyperparameters is not None
                else ArgumentStatus.NOT_APPLICABLE,
            ),
            _ledger(
                "seed",
                request.seed,
                fit_kwargs["random_seed"],
                ArgumentStatus.ACCEPTED,
            ),
        ]
    )

    payload_without_hash = {
        "execution_mode": request.execution_mode.value,
        "selected_model_ids": list(request.model_ids),
        "predictor_kwargs": predictor_kwargs,
        "fit_kwargs": fit_kwargs,
        "argument_ledger": [entry.model_dump(mode="json") for entry in ledger],
    }
    return ExecutionPlan(
        execution_mode=request.execution_mode.value,
        selected_model_ids=request.model_ids,
        predictor_kwargs=predictor_kwargs,
        fit_kwargs=fit_kwargs,
        argument_ledger=tuple(ledger),
        plan_sha256=_canonical_sha256(payload_without_hash),
    )

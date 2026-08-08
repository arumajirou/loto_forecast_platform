from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

from pydantic import ValidationError

from .api_contract import (
    AutoGluonApiContractError,
    validate_hpo_tune_kwargs,
    validate_public_api_kwargs,
)
from .contracts import ProviderRequestV2
from .covariates import ProviderRequestV2Covariates, has_covariate_payload
from .execution import ExecutionPlanError, build_execution_plan
from .provider import ProviderRuntime, _error_response
from .provider import run_provider_v2 as _run_provider_v2


class StrictPreflightError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _source_order(value: Any, *, row_index: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StrictPreflightError(
            "SOURCE_ORDER_TYPE_INVALID",
            f"history row {row_index} source order field {field!r} must be an integer",
        )
    return value


def _source_timestamp(value: Any, *, row_index: int, field: str) -> datetime:
    parsed: datetime
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    elif isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            raise StrictPreflightError(
                "SOURCE_TIMESTAMP_INVALID",
                f"history row {row_index} source timestamp field {field!r} is empty",
            )
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise StrictPreflightError(
                "SOURCE_TIMESTAMP_INVALID",
                f"history row {row_index} source timestamp field {field!r} "
                "must be ISO-8601 compatible",
            ) from exc
    else:
        raise StrictPreflightError(
            "SOURCE_TIMESTAMP_INVALID",
            f"history row {row_index} source timestamp field {field!r} "
            "must be a date, datetime, or ISO-8601 string",
        )
    if parsed.tzinfo is not None and parsed.utcoffset() is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def validate_protocol_v2_preflight(request: ProviderRequestV2) -> None:
    geometry = request.geometry
    if geometry is None:
        return
    if request.predictor.target != "target":
        raise StrictPreflightError(
            "TARGET_COLUMN_NOT_IMPLEMENTED",
            "predictor.target must be 'target' until custom target-column mapping is implemented",
        )
    if request.predictor.freq != geometry.timeline.frequency:
        raise StrictPreflightError(
            "TIMELINE_FREQUENCY_MISMATCH",
            "predictor.freq must equal geometry.timeline.frequency for protocol v2",
        )

    order_field = geometry.timeline.source_order_field
    timestamp_field = geometry.timeline.source_timestamp_field
    previous_order: int | None = None
    previous_timestamp: datetime | None = None
    for row_index, row in enumerate(request.history):
        if order_field not in row or timestamp_field not in row:
            continue
        order = _source_order(row[order_field], row_index=row_index, field=order_field)
        timestamp = _source_timestamp(
            row[timestamp_field],
            row_index=row_index,
            field=timestamp_field,
        )
        if previous_order is not None and order <= previous_order:
            raise StrictPreflightError(
                "SOURCE_ORDER_NOT_STRICTLY_INCREASING",
                "source order values must be strictly increasing in supplied history; "
                "automatic sorting or repair is forbidden",
            )
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            raise StrictPreflightError(
                "SOURCE_TIMESTAMP_NOT_STRICTLY_INCREASING",
                "source timestamp values must be strictly increasing in supplied history; "
                "automatic sorting or repair is forbidden",
            )
        previous_order = order
        previous_timestamp = timestamp


def validate_autogluon_1_5_api_contract(request: ProviderRequestV2) -> None:
    try:
        validate_hpo_tune_kwargs(request.fit.hyperparameter_tune_kwargs)
        plan = build_execution_plan(request)
        predict_kwargs: dict[str, Any] = {"random_seed": request.seed}
        if request.predictor.known_covariates_names:
            predict_kwargs["known_covariates"] = "<TimeSeriesDataFrame>"
        validate_public_api_kwargs(
            predictor_kwargs=plan.predictor_kwargs,
            fit_kwargs=plan.fit_kwargs,
            predict_kwargs=predict_kwargs,
        )
    except ExecutionPlanError:
        raise
    except AutoGluonApiContractError as exc:
        raise StrictPreflightError(
            "AUTOGLUON_API_CONTRACT_MISMATCH",
            str(exc),
        ) from exc


def _strict_error(payload: dict[str, Any], exc: StrictPreflightError) -> dict[str, Any]:
    return _error_response(
        payload,
        code=exc.code,
        phase="strict_preflight",
        message=str(exc),
        error_type=type(exc).__name__,
    )


def run_provider_v2_strict(
    payload: dict[str, Any],
    *,
    runtime: ProviderRuntime | None = None,
) -> dict[str, Any]:
    if has_covariate_payload(payload):
        from .covariate_capability_provider import run_provider_v2_covariates_guarded

        try:
            request = ProviderRequestV2Covariates.model_validate(payload)
        except ValidationError:
            return run_provider_v2_covariates_guarded(payload, runtime=runtime)
        try:
            validate_protocol_v2_preflight(request)
            validate_autogluon_1_5_api_contract(request)
        except ExecutionPlanError:
            return run_provider_v2_covariates_guarded(payload, runtime=runtime)
        except StrictPreflightError as exc:
            return _strict_error(payload, exc)
        return run_provider_v2_covariates_guarded(payload, runtime=runtime)

    try:
        request = ProviderRequestV2.model_validate(payload)
    except ValidationError:
        return _run_provider_v2(payload, runtime=runtime)
    try:
        validate_protocol_v2_preflight(request)
        validate_autogluon_1_5_api_contract(request)
    except ExecutionPlanError:
        return _run_provider_v2(payload, runtime=runtime)
    except StrictPreflightError as exc:
        return _strict_error(payload, exc)
    return _run_provider_v2(payload, runtime=runtime)

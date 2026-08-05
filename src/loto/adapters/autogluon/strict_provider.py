from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

from pydantic import ValidationError

from .contracts import ProviderRequestV2
from .provider import ProviderRuntime, _error_response, run_provider_v2 as _run_provider_v2


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
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def validate_protocol_v2_preflight(request: ProviderRequestV2) -> None:
    geometry = request.geometry
    if geometry is None:
        return
    if request.predictor.target != "target":
        raise StrictPreflightError(
            "TARGET_COLUMN_NOT_IMPLEMENTED",
            "predictor.target must be 'target' until custom target-column mapping "
            "is implemented",
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


def run_provider_v2_strict(
    payload: dict[str, Any],
    *,
    runtime: ProviderRuntime | None = None,
) -> dict[str, Any]:
    try:
        request = ProviderRequestV2.model_validate(payload)
    except ValidationError:
        return _run_provider_v2(payload, runtime=runtime)
    try:
        validate_protocol_v2_preflight(request)
    except StrictPreflightError as exc:
        return _error_response(
            payload,
            code=exc.code,
            phase="strict_preflight",
            message=str(exc),
            error_type=type(exc).__name__,
        )
    return _run_provider_v2(payload, runtime=runtime)

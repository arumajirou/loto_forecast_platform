from __future__ import annotations

import hashlib
import json
import math
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .contracts import CovariatePayload, ProviderRequestV2
from .geometry import CompiledHistory, compile_regular_history
from .provenance import write_json_atomic

COVARIATE_CONTEXT_FILENAME = "loto_covariate_context_v2.json"
_RESERVED_NAMES = {"item_id", "timestamp", "target", "horizon_step"}


class CovariateContractError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class CovariatePayloadV2(CovariatePayload):
    static_features: tuple[dict[str, Any], ...] = ()


class ProviderRequestV2Covariates(ProviderRequestV2):
    covariates: CovariatePayloadV2 = Field(default_factory=CovariatePayloadV2)


class CompiledCovariates(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    history: CompiledHistory
    records: tuple[dict[str, Any], ...]
    future_known_records: tuple[dict[str, Any], ...]
    static_feature_records: tuple[dict[str, Any], ...]
    known_covariate_names: tuple[str, ...]
    past_covariate_names: tuple[str, ...]
    static_feature_names: tuple[str, ...]
    feature_schema: dict[str, str]
    schema_sha256: str
    static_features_sha256: str | None


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def has_covariate_payload(payload: dict[str, Any]) -> bool:
    predictor = payload.get("predictor")
    if isinstance(predictor, dict) and predictor.get("known_covariates_names"):
        return True
    covariates = payload.get("covariates")
    if not isinstance(covariates, dict):
        return False
    return any(
        bool(covariates.get(name))
        for name in (
            "past_covariates_names",
            "static_feature_names",
            "future_known_covariates",
            "static_features",
        )
    )


def _feature_type(value: Any, *, location: str) -> str:
    if value is None:
        raise CovariateContractError(
            "COVARIATE_VALUE_MISSING",
            f"{location} must not be null",
        )
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CovariateContractError(
                "COVARIATE_VALUE_NOT_FINITE",
                f"{location} must be finite",
            )
        return "float"
    if isinstance(value, str):
        if not value.strip():
            raise CovariateContractError(
                "COVARIATE_VALUE_EMPTY",
                f"{location} must not be an empty string",
            )
        return "str"
    raise CovariateContractError(
        "COVARIATE_VALUE_TYPE_UNSUPPORTED",
        f"{location} has unsupported type {type(value).__name__}",
    )


def _validate_names(request: ProviderRequestV2Covariates) -> tuple[tuple[str, ...], ...]:
    assert request.geometry is not None
    known = tuple(request.predictor.known_covariates_names)
    past = tuple(request.covariates.past_covariates_names)
    static = tuple(request.covariates.static_feature_names)
    groups = {"known": known, "past": past, "static": static}
    reserved = {
        *_RESERVED_NAMES,
        *request.geometry.position_columns,
        request.geometry.timeline.source_order_field,
        request.geometry.timeline.source_timestamp_field,
    }
    seen: dict[str, str] = {}
    for group, names in groups.items():
        if len(set(names)) != len(names):
            raise CovariateContractError(
                "COVARIATE_NAMES_NOT_UNIQUE",
                f"{group} covariate names must be unique",
            )
        for name in names:
            if not name or not name.replace("_", "a").isalnum() or name[0].isdigit():
                raise CovariateContractError(
                    "COVARIATE_NAME_INVALID",
                    f"invalid {group} covariate name: {name!r}",
                )
            if name in reserved:
                raise CovariateContractError(
                    "COVARIATE_NAME_RESERVED",
                    f"covariate name {name!r} collides with a reserved field",
                )
            if name in seen:
                raise CovariateContractError(
                    "COVARIATE_ROLE_OVERLAP",
                    f"covariate {name!r} is declared as both {seen[name]} and {group}",
                )
            seen[name] = group
    return known, past, static


def _history_feature_schema(
    request: ProviderRequestV2Covariates,
    names: tuple[str, ...],
) -> dict[str, str]:
    schema: dict[str, str] = {}
    for row_index, row in enumerate(request.history):
        for name in names:
            if name not in row:
                raise CovariateContractError(
                    "HISTORY_COVARIATE_MISSING",
                    f"history row {row_index} is missing covariate {name!r}",
                )
            current = _feature_type(row[name], location=f"history[{row_index}].{name}")
            previous = schema.setdefault(name, current)
            if previous != current:
                raise CovariateContractError(
                    "COVARIATE_DTYPE_MISMATCH",
                    f"history covariate {name!r} changes type from {previous} to {current}",
                )
    return schema


def _compile_future_known(
    request: ProviderRequestV2Covariates,
    known: tuple[str, ...],
) -> tuple[dict[str, Any], ...]:
    assert request.geometry is not None
    rows = request.covariates.future_known_covariates
    if not known:
        if rows:
            raise CovariateContractError(
                "FUTURE_KNOWN_WITHOUT_DECLARATION",
                "future_known_covariates requires predictor.known_covariates_names",
            )
        return ()
    if len(rows) != request.geometry.horizon:
        raise CovariateContractError(
            "FUTURE_KNOWN_HORIZON_MISMATCH",
            "future_known_covariates must contain exactly one global row per horizon step",
        )

    expected_keys = {"horizon_step", *known}
    by_step: dict[int, dict[str, Any]] = {}
    for row_index, row in enumerate(rows):
        keys = set(row)
        if keys != expected_keys:
            missing = sorted(expected_keys - keys)
            unexpected = sorted(keys - expected_keys)
            raise CovariateContractError(
                "FUTURE_KNOWN_SCHEMA_MISMATCH",
                f"future row {row_index} missing={missing} unexpected={unexpected}",
            )
        step = row["horizon_step"]
        if isinstance(step, bool) or not isinstance(step, int):
            raise CovariateContractError(
                "FUTURE_HORIZON_STEP_INVALID",
                f"future row {row_index} horizon_step must be an integer",
            )
        if step < 1 or step > request.geometry.horizon or step in by_step:
            raise CovariateContractError(
                "FUTURE_HORIZON_STEP_INVALID",
                f"future row {row_index} has invalid or duplicate horizon_step={step}",
            )
        for name in known:
            _feature_type(row[name], location=f"future_known[{row_index}].{name}")
        by_step[step] = dict(row)

    records: list[dict[str, Any]] = []
    base = request.geometry.timeline.base_timestamp
    history_length = len(request.history)
    for position_index in range(1, request.geometry.selection_count + 1):
        item_id = f"position-{position_index}"
        for step in range(1, request.geometry.horizon + 1):
            record = {
                "item_id": item_id,
                "timestamp": (base + timedelta(days=history_length + step - 1)).isoformat(),
            }
            record.update({name: by_step[step][name] for name in known})
            records.append(record)
    return tuple(records)


def _compile_static_features(
    request: ProviderRequestV2Covariates,
    static: tuple[str, ...],
) -> tuple[dict[str, Any], ...]:
    assert request.geometry is not None
    rows = request.covariates.static_features
    if not static:
        if rows:
            raise CovariateContractError(
                "STATIC_VALUES_WITHOUT_DECLARATION",
                "static_features requires static_feature_names",
            )
        return ()
    expected_items = {
        f"position-{index}" for index in range(1, request.geometry.selection_count + 1)
    }
    if len(rows) != len(expected_items):
        raise CovariateContractError(
            "STATIC_FEATURE_ITEM_MISMATCH",
            "static_features must contain exactly one row per position item",
        )
    expected_keys = {"item_id", *static}
    compiled: dict[str, dict[str, Any]] = {}
    feature_types: dict[str, str] = {}
    for row_index, row in enumerate(rows):
        keys = set(row)
        if keys != expected_keys:
            missing = sorted(expected_keys - keys)
            unexpected = sorted(keys - expected_keys)
            raise CovariateContractError(
                "STATIC_FEATURE_SCHEMA_MISMATCH",
                f"static row {row_index} missing={missing} unexpected={unexpected}",
            )
        item_id = str(row["item_id"])
        if item_id not in expected_items or item_id in compiled:
            raise CovariateContractError(
                "STATIC_FEATURE_ITEM_MISMATCH",
                f"static row {row_index} has invalid or duplicate item_id={item_id!r}",
            )
        for name in static:
            current = _feature_type(row[name], location=f"static_features[{row_index}].{name}")
            previous = feature_types.setdefault(name, current)
            if previous != current:
                raise CovariateContractError(
                    "COVARIATE_DTYPE_MISMATCH",
                    f"static feature {name!r} changes type from {previous} to {current}",
                )
        compiled[item_id] = dict(row)
    if set(compiled) != expected_items:
        raise CovariateContractError(
            "STATIC_FEATURE_ITEM_MISMATCH",
            "static feature item IDs do not match the expected position items",
        )
    return tuple(compiled[item_id] for item_id in sorted(compiled))


def compile_covariates(request: ProviderRequestV2Covariates) -> CompiledCovariates:
    if request.geometry is None:
        raise CovariateContractError("GEOMETRY_REQUIRED", "geometry is required")
    base_history = compile_regular_history(request.history, request.geometry)
    known, past, static = _validate_names(request)
    schema = _history_feature_schema(request, known + past)
    future = _compile_future_known(request, known)
    static_rows = _compile_static_features(request, static)

    records: list[dict[str, Any]] = []
    for base_record in base_history.records:
        source_index = int(base_record["source_index"])
        source_row = request.history[source_index]
        record = dict(base_record)
        for name in known + past:
            record[name] = source_row[name]
        records.append(record)

    static_hash = canonical_sha256(static_rows) if static_rows else None
    schema_payload = {
        "known_covariate_names": list(known),
        "past_covariate_names": list(past),
        "static_feature_names": list(static),
        "feature_schema": schema,
        "static_features_sha256": static_hash,
    }
    return CompiledCovariates(
        history=base_history,
        records=tuple(records),
        future_known_records=future,
        static_feature_records=static_rows,
        known_covariate_names=known,
        past_covariate_names=past,
        static_feature_names=static,
        feature_schema=schema,
        schema_sha256=canonical_sha256(schema_payload),
        static_features_sha256=static_hash,
    )


def to_time_series_data_frame(compiled: CompiledCovariates, runtime: Any) -> Any:
    columns = [
        "item_id",
        "timestamp",
        "target",
        *compiled.known_covariate_names,
        *compiled.past_covariate_names,
    ]
    frame = pd.DataFrame(compiled.records)[columns].copy()
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    frame["timestamp"] = timestamps.dt.tz_localize(None)
    frame = frame.sort_values(["item_id", "timestamp"]).reset_index(drop=True)
    kwargs: dict[str, Any] = {
        "id_column": "item_id",
        "timestamp_column": "timestamp",
    }
    if compiled.static_feature_records:
        kwargs["static_features_df"] = pd.DataFrame(compiled.static_feature_records)
    return runtime.time_series_data_frame_class.from_data_frame(frame, **kwargs)


def to_known_covariates_data_frame(compiled: CompiledCovariates, runtime: Any) -> Any | None:
    if not compiled.future_known_records:
        return None
    columns = ["item_id", "timestamp", *compiled.known_covariate_names]
    frame = pd.DataFrame(compiled.future_known_records)[columns].copy()
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    frame["timestamp"] = timestamps.dt.tz_localize(None)
    frame = frame.sort_values(["item_id", "timestamp"]).reset_index(drop=True)
    return runtime.time_series_data_frame_class.from_data_frame(
        frame,
        id_column="item_id",
        timestamp_column="timestamp",
    )


def persist_covariate_context(artifact_dir: Path, compiled: CompiledCovariates) -> str:
    path = artifact_dir / COVARIATE_CONTEXT_FILENAME
    payload = {
        "schema_version": 1,
        "known_covariate_names": list(compiled.known_covariate_names),
        "past_covariate_names": list(compiled.past_covariate_names),
        "static_feature_names": list(compiled.static_feature_names),
        "feature_schema": compiled.feature_schema,
        "schema_sha256": compiled.schema_sha256,
        "static_features_sha256": compiled.static_features_sha256,
    }
    write_json_atomic(path, payload)
    return str(path)


def validate_saved_covariate_context(
    artifact_dir: Path,
    compiled: CompiledCovariates,
) -> str:
    path = artifact_dir / COVARIATE_CONTEXT_FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CovariateContractError(
            "COVARIATE_CONTEXT_MISSING",
            f"saved covariate context is missing: {path}",
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise CovariateContractError(
            "COVARIATE_CONTEXT_INVALID",
            f"cannot read saved covariate context: {exc}",
        ) from exc
    if payload.get("schema_version") != 1:
        raise CovariateContractError(
            "COVARIATE_CONTEXT_VERSION_MISMATCH",
            "saved covariate context schema_version must be 1",
        )
    expected = {
        "known_covariate_names": list(compiled.known_covariate_names),
        "past_covariate_names": list(compiled.past_covariate_names),
        "static_feature_names": list(compiled.static_feature_names),
        "feature_schema": compiled.feature_schema,
        "schema_sha256": compiled.schema_sha256,
        "static_features_sha256": compiled.static_features_sha256,
    }
    actual = {key: payload.get(key) for key in expected}
    if actual != expected:
        raise CovariateContractError(
            "COVARIATE_CONTEXT_MISMATCH",
            "saved and requested covariate schemas or static features differ",
        )
    return str(path)

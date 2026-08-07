from __future__ import annotations

import importlib.metadata
import math
import os
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pydantic import ValidationError

from .contracts import (
    DeviceRequest,
    ExecutionMode,
    PredictionRecord,
    ProviderError,
    ProviderOperation,
    ProviderRequestV2,
    ProviderResponseV2,
    RuntimeEvidence,
)
from .execution import ExecutionPlan, ExecutionPlanError, build_execution_plan
from .geometry import CompiledHistory, compile_regular_history
from .inventory import TARGET_AUTOGLUON_VERSION
from .provenance import (
    ArtifactContextError,
    build_fit_context,
    canonical_sha256,
    model_identity_evidence,
    persist_fit_context,
    validate_saved_artifact_context,
)
from .search_spaces import (
    SearchSpaceDescriptorError,
    contains_search_space_descriptor,
    materialize_search_spaces,
    validate_search_space_descriptors,
)


@dataclass(frozen=True, slots=True)
class ProviderRuntime:
    predictor_class: Any
    time_series_data_frame_class: Any
    cuda_available: bool
    library_version: str | None


def _default_runtime(requested_device: DeviceRequest) -> ProviderRuntime:
    if requested_device is DeviceRequest.CPU:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    import torch
    from autogluon.timeseries import TimeSeriesDataFrame, TimeSeriesPredictor

    try:
        library_version = importlib.metadata.version("autogluon.timeseries")
    except importlib.metadata.PackageNotFoundError:
        library_version = None
    return ProviderRuntime(
        predictor_class=TimeSeriesPredictor,
        time_series_data_frame_class=TimeSeriesDataFrame,
        cuda_available=bool(torch.cuda.is_available()),
        library_version=library_version,
    )


def _error_response(
    payload: dict[str, Any],
    *,
    code: str,
    phase: str,
    message: str,
    error_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_operation = str(payload.get("operation", ProviderOperation.DISCOVER.value))
    try:
        operation = ProviderOperation(raw_operation)
    except ValueError:
        operation = ProviderOperation.DISCOVER
    response = ProviderResponseV2(
        run_id=str(payload.get("run_id") or "unknown-run"),
        status="ERROR",
        operation=operation,
        metadata={"raw_operation": raw_operation, **(metadata or {})},
        error=ProviderError(
            code=code,
            phase=phase,
            message=message,
            error_type=error_type,
        ),
    )
    return response.model_dump(mode="json")


def _validate_p4_scope(request: ProviderRequestV2) -> None:
    if request.operation not in {
        ProviderOperation.FIT_PREDICT_SAVE,
        ProviderOperation.LOAD_PREDICT,
    }:
        raise ExecutionPlanError(
            "OPERATION_NOT_IMPLEMENTED_P4",
            "operation",
            f"{request.operation.value} is not implemented by the P4 provider",
        )
    if request.predictor.known_covariates_names:
        raise ExecutionPlanError(
            "KNOWN_COVARIATES_NOT_IMPLEMENTED_P4",
            "predictor.known_covariates_names",
            "known covariate execution is deferred; P4 rejects it instead of dropping it",
        )
    if request.covariates.past_covariates_names:
        raise ExecutionPlanError(
            "PAST_COVARIATES_NOT_IMPLEMENTED_P4",
            "covariates.past_covariates_names",
            "past covariate execution is deferred; P4 rejects it instead of dropping it",
        )
    if request.covariates.static_feature_names:
        raise ExecutionPlanError(
            "STATIC_FEATURES_NOT_IMPLEMENTED_P4",
            "covariates.static_feature_names",
            "static feature execution is deferred; P4 rejects it instead of dropping it",
        )
    if request.covariates.future_known_covariates:
        raise ExecutionPlanError(
            "FUTURE_COVARIATES_NOT_IMPLEMENTED_P4",
            "covariates.future_known_covariates",
            "future known covariate execution is deferred; P4 rejects it instead of dropping it",
        )
    hyperparameters = request.fit.hyperparameters
    try:
        validate_search_space_descriptors(hyperparameters)
    except SearchSpaceDescriptorError as exc:
        raise ExecutionPlanError(
            "INVALID_SEARCH_SPACE_DESCRIPTOR",
            "fit.hyperparameters",
            str(exc),
        ) from exc
    if (
        contains_search_space_descriptor(hyperparameters)
        and request.execution_mode is not ExecutionMode.HPO_SINGLE_MODEL
    ):
        raise ExecutionPlanError(
            "SEARCH_SPACE_WITHOUT_HPO_MODE",
            "fit.hyperparameters",
            "search-space descriptors are only accepted in hpo_single_model mode",
        )


def _to_time_series_data_frame(
    compiled: CompiledHistory,
    runtime: ProviderRuntime,
) -> Any:
    frame = pd.DataFrame(compiled.records)
    frame = frame[["item_id", "timestamp", "target"]].copy()
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    frame["timestamp"] = timestamps.dt.tz_localize(None)
    frame = frame.sort_values(["item_id", "timestamp"]).reset_index(drop=True)
    return runtime.time_series_data_frame_class.from_data_frame(
        frame,
        id_column="item_id",
        timestamp_column="timestamp",
    )


def _prediction_records(
    prediction: Any,
    *,
    expected_items: tuple[str, ...],
    horizon: int,
    expected_quantile_levels: tuple[float, ...],
) -> tuple[PredictionRecord, ...]:
    frame = prediction.reset_index()
    required = {"item_id", "timestamp", "mean"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"prediction output is missing required columns: {missing}")

    frame = frame.sort_values(["item_id", "timestamp"]).reset_index(drop=True)
    actual_items = tuple(sorted(str(value) for value in frame["item_id"].unique()))
    if actual_items != tuple(sorted(expected_items)):
        raise ValueError(
            f"prediction item_ids mismatch expected={sorted(expected_items)} "
            f"actual={list(actual_items)}"
        )
    expected_rows = len(expected_items) * horizon
    if len(frame) != expected_rows:
        raise ValueError(
            f"prediction row count mismatch expected={expected_rows} actual={len(frame)}"
        )

    excluded = {"item_id", "timestamp", "mean"}
    quantile_columns = [column for column in frame.columns if column not in excluded]
    expected_quantiles = {str(level) for level in expected_quantile_levels}
    actual_quantiles = {str(column) for column in quantile_columns}
    if actual_quantiles != expected_quantiles:
        raise ValueError(
            "prediction quantile columns mismatch "
            f"expected={sorted(expected_quantiles)} actual={sorted(actual_quantiles)}"
        )
    records: list[PredictionRecord] = []
    for item_id, group in frame.groupby("item_id", sort=True):
        ordered = group.sort_values("timestamp").reset_index(drop=True)
        if len(ordered) != horizon:
            raise ValueError(
                f"prediction horizon mismatch item_id={item_id!r} "
                f"expected={horizon} actual={len(ordered)}"
            )
        for offset, row in ordered.iterrows():
            mean = float(row["mean"])
            if not math.isfinite(mean):
                raise ValueError(f"prediction mean is not finite for item_id={item_id!r}")
            quantiles: dict[str, float] = {}
            for column in quantile_columns:
                value = float(row[column])
                if not math.isfinite(value):
                    raise ValueError(
                        f"prediction quantile {column!r} is not finite for item_id={item_id!r}"
                    )
                quantiles[str(column)] = value
            timestamp = pd.Timestamp(row["timestamp"]).to_pydatetime()
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            records.append(
                PredictionRecord(
                    item_id=str(item_id),
                    timestamp=timestamp,
                    horizon_step=int(offset) + 1,
                    mean=mean,
                    quantiles=quantiles,
                )
            )
    return tuple(records)


def _safe_model_names(predictor: Any) -> list[str]:
    try:
        return [str(name) for name in predictor.model_names()]
    except Exception:
        return []


def _safe_model_best(predictor: Any) -> str | None:
    try:
        value = predictor.model_best
    except Exception:
        return None
    return None if value is None else str(value)


def _runtime_evidence(
    request: ProviderRequestV2,
    runtime: ProviderRuntime,
) -> RuntimeEvidence:
    requested = request.requested_device
    resolved = "unknown"
    cpu_fallback = False
    if requested is DeviceRequest.CPU:
        resolved = "cpu"
    elif not runtime.cuda_available:
        resolved = "cpu"
        cpu_fallback = requested is DeviceRequest.CUDA
    return RuntimeEvidence(
        requested_device=requested,
        resolved_device=resolved,
        cuda_available=runtime.cuda_available,
        gpu_used=False,
        cpu_fallback=cpu_fallback,
        pid=os.getpid(),
        evidence_status="PARTIAL",
    )


def _validate_library_version(runtime: ProviderRuntime) -> None:
    if runtime.library_version != TARGET_AUTOGLUON_VERSION:
        raise ArtifactContextError(
            "RUNTIME_VERSION_MISMATCH",
            "AutoGluon TimeSeries runtime version mismatch: "
            f"expected={TARGET_AUTOGLUON_VERSION} actual={runtime.library_version}",
        )


def _validate_observed_model_identity(
    plan: ExecutionPlan,
    observed_model_names: list[str],
) -> dict[str, Any]:
    identity = model_identity_evidence(plan.selected_model_ids, observed_model_names)
    if identity["verified"] is not True:
        raise ArtifactContextError(
            "MODEL_IDENTITY_NOT_VERIFIED",
            "runtime model names do not prove every requested model identity: "
            f"missing={identity['missing_model_ids']} observed={observed_model_names}",
        )
    return identity


def run_provider_v2(
    payload: dict[str, Any],
    *,
    runtime: ProviderRuntime | None = None,
) -> dict[str, Any]:
    try:
        request = ProviderRequestV2.model_validate(payload)
    except ValidationError as exc:
        return _error_response(
            payload,
            code="CONTRACT_VALIDATION_FAILED",
            phase="request_validation",
            message=str(exc),
            error_type=type(exc).__name__,
        )

    try:
        _validate_p4_scope(request)
        plan = build_execution_plan(request)
    except ExecutionPlanError as exc:
        return _error_response(
            payload,
            code=exc.code,
            phase="execution_plan",
            message=str(exc),
            error_type=type(exc).__name__,
            metadata={"argument": exc.argument},
        )

    assert request.geometry is not None
    assert request.artifact_dir is not None
    try:
        compiled = compile_regular_history(request.history, request.geometry)
    except Exception as exc:
        return _error_response(
            payload,
            code="HISTORY_COMPILATION_FAILED",
            phase="history_compilation",
            message=str(exc),
            error_type=type(exc).__name__,
        )

    try:
        active_runtime = runtime or _default_runtime(request.requested_device)
        _validate_library_version(active_runtime)
    except ArtifactContextError as exc:
        return _error_response(
            payload,
            code=exc.code,
            phase="runtime_import",
            message=str(exc),
            error_type=type(exc).__name__,
            metadata={
                "expected_library_version": TARGET_AUTOGLUON_VERSION,
                "actual_library_version": getattr(active_runtime, "library_version", None),
            },
        )
    except Exception as exc:
        return _error_response(
            payload,
            code="RUNTIME_IMPORT_FAILED",
            phase="runtime_import",
            message=str(exc),
            error_type=type(exc).__name__,
        )

    artifact_dir = Path(request.artifact_dir)
    saved_context = None
    try:
        time_series = _to_time_series_data_frame(compiled, active_runtime)
        if request.operation is ProviderOperation.FIT_PREDICT_SAVE:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            if any(artifact_dir.iterdir()):
                raise FileExistsError(
                    f"artifact_dir must be empty for fit_predict_save: {artifact_dir}"
                )
            predictor = active_runtime.predictor_class(**plan.predictor_kwargs)
            fit_kwargs = dict(plan.fit_kwargs)
            hyperparameters = fit_kwargs.get("hyperparameters")
            if contains_search_space_descriptor(hyperparameters):
                from autogluon.common import space as autogluon_space

                fit_kwargs["hyperparameters"] = materialize_search_spaces(
                    hyperparameters,
                    space_module=autogluon_space,
                )
            predictor.fit(time_series, **fit_kwargs)
        else:
            if not artifact_dir.exists() or not any(artifact_dir.iterdir()):
                raise FileNotFoundError(
                    f"artifact_dir not found or empty for load_predict: {artifact_dir}"
                )
            saved_context = validate_saved_artifact_context(
                artifact_dir,
                current_execution_plan=plan.to_dict(),
                current_geometry_sha256=compiled.geometry_sha256,
                expected_library_version=TARGET_AUTOGLUON_VERSION,
            )
            predictor = active_runtime.predictor_class.load(str(artifact_dir))

        prediction = predictor.predict(time_series, random_seed=request.seed)
        expected_items = tuple(
            f"position-{index}"
            for index in range(1, request.geometry.selection_count + 1)
        )
        records = _prediction_records(
            prediction,
            expected_items=expected_items,
            horizon=request.geometry.horizon,
            expected_quantile_levels=request.predictor.quantile_levels,
        )
        model_names = _safe_model_names(predictor)
        model_best = _safe_model_best(predictor)
        identity = _validate_observed_model_identity(plan, model_names)

        if request.operation is ProviderOperation.FIT_PREDICT_SAVE:
            context = build_fit_context(
                run_id=request.run_id,
                request_payload=request.model_dump(mode="json"),
                execution_plan=plan.to_dict(),
                timeline_mapping=[
                    row.model_dump(mode="json") for row in compiled.timeline_mapping
                ],
                source_order_sha256=compiled.source_order_sha256,
                timeline_mapping_sha256=compiled.mapping_sha256,
                geometry_sha256=compiled.geometry_sha256,
                library_version=TARGET_AUTOGLUON_VERSION,
                model_names=model_names,
                model_best=model_best,
            )
            artifacts = persist_fit_context(artifact_dir, context=context)
            saved_context_sha256 = canonical_sha256(context)
        else:
            assert saved_context is not None
            saved_names = saved_context.context["runtime_snapshot"]["model_names"]
            if sorted(model_names) != sorted(str(name) for name in saved_names):
                raise ArtifactContextError(
                    "LOADED_MODEL_SET_MISMATCH",
                    "loaded predictor model names differ from the saved runtime snapshot",
                )
            artifacts = saved_context.artifacts
            saved_context_sha256 = canonical_sha256(saved_context.context)
    except Exception as exc:
        message = str(exc)
        lower = message.lower()
        code = "PROVIDER_EXECUTION_FAILED"
        if isinstance(exc, ArtifactContextError):
            code = exc.code
        elif "license" in lower or "gated" in lower:
            code = "LICENSE_RESTRICTED"
        elif isinstance(exc, FileNotFoundError):
            code = "ARTIFACT_MISSING"
        elif isinstance(exc, FileExistsError):
            code = "ARTIFACT_DIR_NOT_EMPTY"
        elif "prediction" in lower:
            code = "PREDICTION_CONTRACT_FAILED"
        return _error_response(
            payload,
            code=code,
            phase="fit_load_predict",
            message=message,
            error_type=type(exc).__name__,
            metadata={"plan_sha256": plan.plan_sha256},
        )

    request_payload = request.model_dump(mode="json")
    metadata = {
        "library": "autogluon.timeseries",
        "library_version": active_runtime.library_version,
        "execution_mode": request.execution_mode.value,
        "selected_model_ids": list(plan.selected_model_ids),
        "observed_model_names": model_names,
        "model_identity": identity,
        "model_identity_verified": identity["verified"],
        "plan_sha256": plan.plan_sha256,
        "request_sha256": canonical_sha256(request_payload),
        "saved_context_sha256": saved_context_sha256,
        "source_order_sha256": compiled.source_order_sha256,
        "timeline_mapping_sha256": compiled.mapping_sha256,
        "geometry_sha256": compiled.geometry_sha256,
        "prediction_shape": [request.geometry.selection_count, request.geometry.horizon],
        "prediction_random_seed": request.seed,
        "model_best": model_best,
        "model_names": model_names,
        "finite": bool(
            np.isfinite(np.asarray([record.mean for record in records], dtype=float)).all()
        ),
    }
    response = ProviderResponseV2(
        run_id=request.run_id,
        status="OK",
        operation=request.operation,
        predictions=records,
        argument_ledger=plan.argument_ledger,
        artifacts=artifacts,
        metadata=metadata,
        runtime_evidence=_runtime_evidence(request, active_runtime),
    )
    return response.model_dump(mode="json")

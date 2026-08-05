from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from pydantic import ValidationError

from .contracts import ExecutionMode, ProviderOperation, ProviderResponseV2
from .covariates import (
    CovariateContractError,
    ProviderRequestV2Covariates,
    compile_covariates,
    persist_covariate_context,
    to_known_covariates_data_frame,
    to_time_series_data_frame,
    validate_saved_covariate_context,
)
from .execution import ExecutionPlanError, build_execution_plan
from .inventory import TARGET_AUTOGLUON_VERSION
from .provenance import (
    ArtifactContextError,
    build_fit_context,
    canonical_sha256,
    persist_fit_context,
    validate_saved_artifact_context,
)
from .provider import (
    ProviderRuntime,
    _default_runtime,
    _error_response,
    _prediction_records,
    _runtime_evidence,
    _safe_model_best,
    _safe_model_names,
    _validate_library_version,
    _validate_observed_model_identity,
)
from .search_spaces import (
    SearchSpaceDescriptorError,
    contains_search_space_descriptor,
    materialize_search_spaces,
    validate_search_space_descriptors,
)


def _validate_covariate_scope(request: ProviderRequestV2Covariates) -> None:
    if request.operation not in {
        ProviderOperation.FIT_PREDICT_SAVE,
        ProviderOperation.LOAD_PREDICT,
    }:
        raise ExecutionPlanError(
            "OPERATION_NOT_IMPLEMENTED_P13",
            "operation",
            f"{request.operation.value} is not implemented by the P13 covariate provider",
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


def run_provider_v2_covariates(
    payload: dict[str, Any],
    *,
    runtime: ProviderRuntime | None = None,
) -> dict[str, Any]:
    try:
        request = ProviderRequestV2Covariates.model_validate(payload)
    except ValidationError as exc:
        return _error_response(
            payload,
            code="CONTRACT_VALIDATION_FAILED",
            phase="request_validation",
            message=str(exc),
            error_type=type(exc).__name__,
        )

    try:
        _validate_covariate_scope(request)
        plan = build_execution_plan(request)
        compiled = compile_covariates(request)
    except ExecutionPlanError as exc:
        return _error_response(
            payload,
            code=exc.code,
            phase="execution_plan",
            message=str(exc),
            error_type=type(exc).__name__,
            metadata={"argument": exc.argument},
        )
    except CovariateContractError as exc:
        return _error_response(
            payload,
            code=exc.code,
            phase="covariate_compilation",
            message=str(exc),
            error_type=type(exc).__name__,
        )
    except Exception as exc:
        return _error_response(
            payload,
            code="HISTORY_COMPILATION_FAILED",
            phase="history_compilation",
            message=str(exc),
            error_type=type(exc).__name__,
        )

    assert request.geometry is not None
    assert request.artifact_dir is not None
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
        time_series = to_time_series_data_frame(compiled, active_runtime)
        known_covariates = to_known_covariates_data_frame(compiled, active_runtime)
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
                current_geometry_sha256=compiled.history.geometry_sha256,
                expected_library_version=TARGET_AUTOGLUON_VERSION,
            )
            validate_saved_covariate_context(artifact_dir, compiled)
            predictor = active_runtime.predictor_class.load(str(artifact_dir))

        predict_kwargs: dict[str, Any] = {"random_seed": request.seed}
        if known_covariates is not None:
            predict_kwargs["known_covariates"] = known_covariates
        prediction = predictor.predict(time_series, **predict_kwargs)
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
                    row.model_dump(mode="json") for row in compiled.history.timeline_mapping
                ],
                source_order_sha256=compiled.history.source_order_sha256,
                timeline_mapping_sha256=compiled.history.mapping_sha256,
                geometry_sha256=compiled.history.geometry_sha256,
                library_version=TARGET_AUTOGLUON_VERSION,
                model_names=model_names,
                model_best=model_best,
            )
            artifacts = persist_fit_context(artifact_dir, context=context)
            artifacts["covariate_context"] = persist_covariate_context(
                artifact_dir,
                compiled,
            )
            saved_context_sha256 = canonical_sha256(context)
        else:
            assert saved_context is not None
            saved_names = saved_context.context["runtime_snapshot"]["model_names"]
            if sorted(model_names) != sorted(str(name) for name in saved_names):
                raise ArtifactContextError(
                    "LOADED_MODEL_SET_MISMATCH",
                    "loaded predictor model names differ from the saved runtime snapshot",
                )
            artifacts = dict(saved_context.artifacts)
            artifacts["covariate_context"] = str(
                artifact_dir / "loto_covariate_context_v2.json"
            )
            saved_context_sha256 = canonical_sha256(saved_context.context)
    except Exception as exc:
        message = str(exc)
        lower = message.lower()
        code = "PROVIDER_EXECUTION_FAILED"
        if isinstance(exc, (ArtifactContextError, CovariateContractError)):
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

    metadata = {
        "library": "autogluon.timeseries",
        "library_version": active_runtime.library_version,
        "execution_mode": request.execution_mode.value,
        "selected_model_ids": list(plan.selected_model_ids),
        "observed_model_names": model_names,
        "model_identity": identity,
        "model_identity_verified": identity["verified"],
        "plan_sha256": plan.plan_sha256,
        "request_sha256": canonical_sha256(request.model_dump(mode="json")),
        "saved_context_sha256": saved_context_sha256,
        "source_order_sha256": compiled.history.source_order_sha256,
        "timeline_mapping_sha256": compiled.history.mapping_sha256,
        "geometry_sha256": compiled.history.geometry_sha256,
        "covariate_schema_sha256": compiled.schema_sha256,
        "static_features_sha256": compiled.static_features_sha256,
        "known_covariate_names": list(compiled.known_covariate_names),
        "past_covariate_names": list(compiled.past_covariate_names),
        "static_feature_names": list(compiled.static_feature_names),
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

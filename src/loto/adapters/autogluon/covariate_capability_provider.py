from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .contracts import ProviderOperation
from .covariate_capabilities import (
    CovariateCapabilityDecision,
    CovariateCapabilityError,
    build_covariate_capability_decision,
    requested_roles,
)
from .covariate_provider import run_provider_v2_covariates
from .covariates import ProviderRequestV2Covariates
from .execution import ExecutionPlanError, build_execution_plan
from .inventory import TARGET_AUTOGLUON_VERSION
from .provenance import canonical_sha256, write_json_atomic
from .provider import ProviderRuntime, _error_response

CAPABILITY_CONTEXT_FILENAME = "loto_covariate_capability_v2.json"


def build_request_capability_decision(
    request: ProviderRequestV2Covariates,
) -> CovariateCapabilityDecision:
    plan = build_execution_plan(request)
    hyperparameters = plan.fit_kwargs.get("hyperparameters")
    if not isinstance(hyperparameters, dict):
        raise CovariateCapabilityError(
            "COVARIATE_EFFECTIVE_HYPERPARAMETERS_INVALID",
            "effective model hyperparameters must be a dictionary",
        )
    roles = requested_roles(
        known_covariate_names=request.predictor.known_covariates_names,
        past_covariate_names=request.covariates.past_covariates_names,
        static_feature_names=request.covariates.static_feature_names,
    )
    return build_covariate_capability_decision(
        execution_mode=request.execution_mode.value,
        selected_model_ids=plan.selected_model_ids,
        model_hyperparameters=hyperparameters,
        roles=roles,
    )


def persist_capability_context(
    artifact_dir: Path,
    decision: CovariateCapabilityDecision,
) -> str:
    path = artifact_dir / CAPABILITY_CONTEXT_FILENAME
    write_json_atomic(
        path,
        {
            "schema_version": 1,
            "autogluon_version": TARGET_AUTOGLUON_VERSION,
            "decision": decision.to_dict(),
        },
    )
    return str(path)


def validate_saved_capability_context(
    artifact_dir: Path,
    decision: CovariateCapabilityDecision,
) -> str:
    path = artifact_dir / CAPABILITY_CONTEXT_FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CovariateCapabilityError(
            "COVARIATE_CAPABILITY_CONTEXT_MISSING",
            f"saved covariate capability context is missing: {path}",
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise CovariateCapabilityError(
            "COVARIATE_CAPABILITY_CONTEXT_INVALID",
            f"cannot read saved covariate capability context: {exc}",
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise CovariateCapabilityError(
            "COVARIATE_CAPABILITY_CONTEXT_VERSION_MISMATCH",
            "saved covariate capability context schema_version must be 1",
        )
    if payload.get("autogluon_version") != TARGET_AUTOGLUON_VERSION:
        raise CovariateCapabilityError(
            "COVARIATE_CAPABILITY_VERSION_MISMATCH",
            "saved capability context AutoGluon version does not match the runtime contract",
        )
    saved = payload.get("decision")
    if not isinstance(saved, dict):
        raise CovariateCapabilityError(
            "COVARIATE_CAPABILITY_CONTEXT_INVALID",
            "saved capability context has no decision object",
        )
    saved_without_hash = dict(saved)
    saved_hash = saved_without_hash.pop("decision_sha256", None)
    if saved_hash != canonical_sha256(saved_without_hash):
        raise CovariateCapabilityError(
            "COVARIATE_CAPABILITY_HASH_MISMATCH",
            "saved capability decision SHA-256 does not match its payload",
        )
    if saved != decision.to_dict():
        raise CovariateCapabilityError(
            "COVARIATE_CAPABILITY_CONTEXT_MISMATCH",
            "saved and requested model covariate capability decisions differ",
        )
    return str(path)


def _capability_error_response(
    payload: dict[str, Any],
    exc: CovariateCapabilityError,
) -> dict[str, Any]:
    metadata = {
        "model_id": exc.model_id,
        "covariate_role": exc.role,
    }
    return _error_response(
        payload,
        code=exc.code,
        phase="covariate_capability",
        message=str(exc),
        error_type=type(exc).__name__,
        metadata=metadata,
    )


def run_provider_v2_covariates_guarded(
    payload: dict[str, Any],
    *,
    runtime: ProviderRuntime | None = None,
) -> dict[str, Any]:
    try:
        request = ProviderRequestV2Covariates.model_validate(payload)
    except ValidationError:
        return run_provider_v2_covariates(payload, runtime=runtime)
    try:
        decision = build_request_capability_decision(request)
    except ExecutionPlanError:
        return run_provider_v2_covariates(payload, runtime=runtime)
    except CovariateCapabilityError as exc:
        return _capability_error_response(payload, exc)

    assert request.artifact_dir is not None
    artifact_dir = Path(request.artifact_dir)
    if request.operation is ProviderOperation.LOAD_PREDICT:
        try:
            validate_saved_capability_context(artifact_dir, decision)
        except CovariateCapabilityError as exc:
            return _capability_error_response(payload, exc)

    response = run_provider_v2_covariates(payload, runtime=runtime)
    if response.get("status") != "OK":
        return response
    try:
        if request.operation is ProviderOperation.FIT_PREDICT_SAVE:
            context_path = persist_capability_context(artifact_dir, decision)
        else:
            context_path = str(artifact_dir / CAPABILITY_CONTEXT_FILENAME)
    except Exception as exc:
        return _error_response(
            payload,
            code="COVARIATE_CAPABILITY_CONTEXT_WRITE_FAILED",
            phase="covariate_capability",
            message=str(exc),
            error_type=type(exc).__name__,
        )

    result = dict(response)
    metadata = dict(result.get("metadata") or {})
    metadata["covariate_capability_decision"] = decision.to_dict()
    metadata["covariate_capability_sha256"] = decision.decision_sha256
    result["metadata"] = metadata
    artifacts = dict(result.get("artifacts") or {})
    artifacts["covariate_capability_context"] = context_path
    result["artifacts"] = artifacts
    return result

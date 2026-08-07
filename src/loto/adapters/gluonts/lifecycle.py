from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .protocol import (
    GluonTSProviderRequest,
    ProviderOperation,
    ProviderStatus,
)
from .runner import ProviderInvocation, atomic_write_json, invoke_provider, sha256_file
from .serialization import (
    LifecycleOutcome,
    PredictorFitSerializeResult,
    PredictorLifecycleResult,
    PredictorReloadResult,
    fit_result_sha256,
    lifecycle_result_sha256,
    reload_result_sha256,
)


@dataclass(frozen=True)
class LifecycleInvocation:
    result: PredictorLifecycleResult
    fit_invocation: ProviderInvocation
    load_invocation: ProviderInvocation | None
    result_path: Path
    result_sha256: str
    manifest_path: Path
    manifest_sha256: str


def _provider_fit_result(invocation: ProviderInvocation) -> PredictorFitSerializeResult:
    raw = invocation.response.metadata.get("predictor_fit_serialize")
    declared_sha = invocation.response.metadata.get("predictor_fit_serialize_sha256")
    result = PredictorFitSerializeResult.model_validate(raw)
    calculated_sha = fit_result_sha256(result)
    if declared_sha != calculated_sha:
        raise ValueError("provider fit/serialize result SHA-256 mismatch")
    return result


def _provider_reload_result(invocation: ProviderInvocation) -> PredictorReloadResult:
    raw = invocation.response.metadata.get("predictor_reload")
    declared_sha = invocation.response.metadata.get("predictor_reload_sha256")
    result = PredictorReloadResult.model_validate(raw)
    calculated_sha = reload_result_sha256(result)
    if declared_sha != calculated_sha:
        raise ValueError("provider reload result SHA-256 mismatch")
    return result


def _aggregate_outcome(
    fit: PredictorFitSerializeResult,
    reload: PredictorReloadResult | None,
) -> LifecycleOutcome:
    if fit.outcome is not LifecycleOutcome.VERIFIED:
        return fit.outcome
    if reload is None:
        return LifecycleOutcome.FAILED
    return reload.outcome


def certify_predictor_lifecycle(
    request: GluonTSProviderRequest,
    command: Sequence[str],
    artifact_root: Path,
    predictor_artifact_dir: Path,
    *,
    timeout_seconds: float = 600.0,
    invoke: Callable[..., ProviderInvocation] = invoke_provider,
) -> LifecycleInvocation:
    """Run fit/serialize and reload/predict in two distinct provider processes."""

    if request.operation is not ProviderOperation.FIT_PREDICT:
        raise ValueError("P5 lifecycle requires a fit_predict request")
    if not request.dataset:
        raise ValueError("P5 lifecycle requires a non-empty dataset")
    predictor_artifact_dir = predictor_artifact_dir.resolve()
    fit_request = request.model_copy(
        update={"artifact_dir": str(predictor_artifact_dir)}
    )
    fit_invocation = invoke(
        fit_request,
        command,
        artifact_root,
        timeout_seconds=timeout_seconds,
    )
    fit = _provider_fit_result(fit_invocation)
    load_invocation: ProviderInvocation | None = None
    reload: PredictorReloadResult | None = None

    if fit.outcome is LifecycleOutcome.VERIFIED:
        load_request = fit_request.model_copy(
            update={
                "request_id": f"{fit_request.request_id}-reload",
                "operation": ProviderOperation.LOAD_PREDICT,
                "dataset": [],
                "arguments": {
                    **fit_request.arguments,
                    "p5_reload_certification": True,
                },
            }
        )
        load_invocation = invoke(
            load_request,
            command,
            artifact_root,
            timeout_seconds=timeout_seconds,
        )
        reload = _provider_reload_result(load_invocation)

    outcome = _aggregate_outcome(fit, reload)
    errors = list(fit.errors)
    if reload is not None:
        errors.extend(reload.errors)
    if outcome is LifecycleOutcome.FAILED and not errors:
        errors.append("P5 lifecycle failed without provider error detail")
    if outcome is LifecycleOutcome.BLOCKED and not errors:
        errors.append("P5 lifecycle is blocked")

    result = PredictorLifecycleResult(
        lane=request.lane.value,
        outcome=outcome,
        fit_request_id=fit_request.request_id,
        load_request_id=(
            f"{fit_request.request_id}-reload"
            if load_invocation is not None
            else "not-run"
        ),
        fit=fit,
        reload=reload,
        artifact_manifest_sha256=fit.artifact_manifest_sha256,
        errors=[] if outcome is LifecycleOutcome.VERIFIED else errors,
    )
    lifecycle_dir = artifact_root / request.run_id / "p5-lifecycle"
    result_path = lifecycle_dir / "predictor_lifecycle.json"
    result_sha = atomic_write_json(result_path, result.model_dump(mode="json"))
    if result_sha != lifecycle_result_sha256(result):
        raise ValueError("persisted P5 lifecycle SHA-256 mismatch")

    manifest = {
        "schema_version": 1,
        "lane": request.lane.value,
        "fit_request_id": fit_request.request_id,
        "load_request_id": (
            load_invocation.response.request_id
            if load_invocation is not None
            else None
        ),
        "fit_response_sha256": fit_invocation.response_sha256,
        "load_response_sha256": (
            load_invocation.response_sha256
            if load_invocation is not None
            else None
        ),
        "predictor_artifact_manifest_sha256": fit.artifact_manifest_sha256,
        "predictor_lifecycle_sha256": result_sha,
        "fit_return_code": fit_invocation.return_code,
        "load_return_code": (
            load_invocation.return_code
            if load_invocation is not None
            else None
        ),
    }
    manifest_path = lifecycle_dir / "lifecycle_manifest.json"
    manifest_sha = atomic_write_json(manifest_path, manifest)
    if manifest_sha != sha256_file(manifest_path):
        raise ValueError("persisted lifecycle manifest SHA-256 mismatch")

    if outcome is LifecycleOutcome.VERIFIED:
        if fit_invocation.response.status is ProviderStatus.FAILED:
            raise ValueError("VERIFIED lifecycle cannot have failed fit response")
        if load_invocation is None:
            raise ValueError("VERIFIED lifecycle requires load invocation")
        if load_invocation.response.status is ProviderStatus.FAILED:
            raise ValueError("VERIFIED lifecycle cannot have failed load response")

    return LifecycleInvocation(
        result=result,
        fit_invocation=fit_invocation,
        load_invocation=load_invocation,
        result_path=result_path,
        result_sha256=result_sha,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha,
    )

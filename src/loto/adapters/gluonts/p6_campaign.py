from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .p6_contract import (
    FIT_CHECKS,
    FailureCategory,
    P6CampaignResult,
    P6CheckState,
    P6DatasetItem,
    P6ModelLifecycle,
    P6Operation,
    P6ProviderRequest,
    P6ProviderResponse,
    P6StageEvidence,
    P6Status,
    atomic_write_json,
    sha256_json,
)
from .p6_registry import model_specs, registry_sha256


@dataclass(frozen=True)
class StageInvocation:
    response: P6ProviderResponse
    return_code: int
    request_path: Path
    response_path: Path
    stdout_path: Path
    stderr_path: Path
    request_sha256: str
    response_sha256: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def invoke_p6_provider(
    request: P6ProviderRequest,
    command: Sequence[str],
    artifact_root: Path,
    timeout_seconds: float = 600.0,
) -> StageInvocation:
    if not command:
        raise ValueError("provider command cannot be empty")
    artifact_root = artifact_root.resolve()
    run_dir = artifact_root / request.model_class / request.operation.value
    request_path = run_dir / "request.json"
    response_path = run_dir / "response.json"
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    request_sha = atomic_write_json(request_path, request.model_dump(mode="json"))
    completed = subprocess.run(
        [*command, "--request", str(request_path), "--response", str(response_path)],
        cwd=run_dir,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        env={
            **os.environ,
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "PYTHONHASHSEED": str(request.seed),
            # P6 is intentionally CPU-pinned. GluonTS predictors can
            # independently auto-select CUDA even when Lightning training
            # uses accelerator="cpu", so hide CUDA from provider processes.
            "CUDA_VISIBLE_DEVICES": "",
        },
    )
    _atomic_write_bytes(stdout_path, completed.stdout.encode("utf-8"))
    _atomic_write_bytes(stderr_path, completed.stderr.encode("utf-8"))
    if not response_path.exists():
        raise RuntimeError(
            f"provider exited {completed.returncode} without response for {request.model_class}"
        )
    response = P6ProviderResponse.model_validate_json(response_path.read_text("utf-8"))
    if (
        response.request_id != request.request_id
        or response.run_id != request.run_id
        or response.lane != request.lane
        or response.evidence.model_class != request.model_class
        or response.evidence.operation != request.operation
    ):
        raise RuntimeError("provider response identity mismatch")
    return StageInvocation(
        response=response,
        return_code=completed.returncode,
        request_path=request_path,
        response_path=response_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        request_sha256=request_sha,
        response_sha256=_sha256_file(response_path),
    )


def certification_dataset() -> P6DatasetItem:
    return P6DatasetItem(
        item_id="p6-certification-series",
        start="2000-01-01",
        target=[float((index % 9) + index / 100.0) for index in range(64)],
    )


def _model_lifecycle(
    *,
    run_id: str,
    lane: str,
    spec: Any,
    command: Sequence[str],
    artifact_root: Path,
    invoker: Callable[[P6ProviderRequest, Sequence[str], Path, float], StageInvocation],
    timeout_seconds: float,
) -> P6ModelLifecycle:
    predictor_dir = artifact_root / "predictors" / spec.model_class
    fit_request = P6ProviderRequest(
        request_id=f"{run_id}-{spec.model_class}-fit",
        run_id=run_id,
        lane=lane,
        operation=P6Operation.FIT_SERIALIZE,
        model_class=spec.model_class,
        distribution_output=spec.certified_distributions[0],
        prediction_length=1,
        context_length=(spec.default_context_length if spec.supports_context_length else None),
        seed=1,
        freq="D",
        artifact_dir=str(predictor_dir),
        dataset=[certification_dataset()],
        threads_per_job=1,
    )
    fit = invoker(fit_request, command, artifact_root / "provider", timeout_seconds)
    if fit.response.status is not P6Status.VERIFIED:
        return P6ModelLifecycle(
            model_class=spec.model_class,
            status=fit.response.status,
            fit=fit.response,
            errors=list(fit.response.errors),
        )
    load_request = P6ProviderRequest(
        request_id=f"{run_id}-{spec.model_class}-load",
        run_id=run_id,
        lane=lane,
        operation=P6Operation.LOAD_PREDICT,
        model_class=spec.model_class,
        distribution_output=spec.certified_distributions[0],
        prediction_length=1,
        context_length=(spec.default_context_length if spec.supports_context_length else None),
        seed=1,
        freq="D",
        artifact_dir=str(predictor_dir),
        dataset=[],
        threads_per_job=1,
    )
    reload = invoker(load_request, command, artifact_root / "provider", timeout_seconds)
    if reload.response.status is not P6Status.VERIFIED:
        return P6ModelLifecycle(
            model_class=spec.model_class,
            status=reload.response.status,
            fit=fit.response,
            reload=reload.response,
            errors=list(reload.response.errors),
        )
    return P6ModelLifecycle(
        model_class=spec.model_class,
        status=P6Status.VERIFIED,
        fit=fit.response,
        reload=reload.response,
    )


def _crashed_lifecycle(
    *,
    run_id: str,
    lane: str,
    model_class: str,
    error: str,
) -> P6ModelLifecycle:
    spec = next(spec for spec in model_specs() if spec.model_class == model_class)
    evidence = P6StageEvidence(
        lane=lane,
        operation=P6Operation.FIT_SERIALIZE,
        model_class=model_class,
        distribution_output=spec.certified_distributions[0],
        status=P6Status.FAILED,
        process_id=max(1, os.getpid()),
        prediction_length=1,
        expected_shape=[1],
        failure_category=FailureCategory.UNKNOWN,
        checks={name: P6CheckState.NOT_RUN for name in FIT_CHECKS},
        errors=[error],
    )
    response = P6ProviderResponse(
        request_id=f"{run_id}-{model_class}-fit",
        run_id=run_id,
        lane=lane,
        status=P6Status.FAILED,
        evidence=evidence,
        errors=[error],
    )
    return P6ModelLifecycle(
        model_class=model_class,
        status=P6Status.FAILED,
        fit=response,
        errors=[error],
    )


def run_p6_campaign(
    *,
    run_id: str,
    lane: str,
    command: Sequence[str],
    artifact_root: Path,
    workers: int = 8,
    timeout_seconds: float = 600.0,
    invoker: Callable[
        [P6ProviderRequest, Sequence[str], Path, float],
        StageInvocation,
    ] = invoke_p6_provider,
) -> P6CampaignResult:
    if lane not in {"compat", "latest"}:
        raise ValueError("lane must be compat or latest")
    if workers < 1 or workers > 8:
        raise ValueError("P6 campaign workers must be in the range 1..8")
    artifact_root = artifact_root.resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    futures = {}
    results: dict[str, P6ModelLifecycle] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for spec in model_specs():
            future = executor.submit(
                _model_lifecycle,
                run_id=run_id,
                lane=lane,
                spec=spec,
                command=command,
                artifact_root=artifact_root,
                invoker=invoker,
                timeout_seconds=timeout_seconds,
            )
            futures[future] = spec.model_class
        for future in as_completed(futures):
            model_class = futures[future]
            try:
                results[model_class] = future.result()
            except Exception as exc:
                results[model_class] = _crashed_lifecycle(
                    run_id=run_id,
                    lane=lane,
                    model_class=model_class,
                    error=f"{type(exc).__name__}: {exc}",
                )
    ordered = [results[spec.model_class] for spec in model_specs()]
    statuses = {model.status for model in ordered}
    if statuses == {P6Status.VERIFIED}:
        status = P6Status.VERIFIED
        errors: list[str] = []
    elif P6Status.FAILED in statuses:
        status = P6Status.FAILED
        errors = ["one or more model lifecycles failed"]
    elif statuses == {P6Status.BLOCKED}:
        status = P6Status.BLOCKED
        errors = ["all nine model lifecycles are blocked"]
    else:
        status = P6Status.PARTIALLY_VERIFIED
        errors = ["P6 campaign has mixed verified and blocked results"]
    campaign = P6CampaignResult(
        run_id=run_id,
        lane=lane,
        status=status,
        workers=workers,
        registry_sha256=registry_sha256(),
        models=ordered,
        errors=errors,
    )
    result_path = artifact_root / "p6_campaign_result.json"
    result_sha = atomic_write_json(result_path, campaign.model_dump(mode="json"))
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "lane": lane,
        "workers": workers,
        "registry_sha256": registry_sha256(),
        "campaign_result_sha256": result_sha,
        "campaign_payload_sha256": sha256_json(campaign.model_dump(mode="json")),
        "model_statuses": {model.model_class: model.status.value for model in ordered},
    }
    atomic_write_json(artifact_root / "p6_campaign_manifest.json", manifest)
    return campaign

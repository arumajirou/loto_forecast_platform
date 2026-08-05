from __future__ import annotations

from pathlib import Path
from typing import Sequence

from loto.adapters.gluonts.p6_campaign import StageInvocation, run_p6_campaign
from loto.adapters.gluonts.p6_contract import (
    FIT_CHECKS,
    LOAD_CHECKS,
    ArtifactFile,
    FailureCategory,
    P6CheckState,
    P6Operation,
    P6PredictorManifest,
    P6ProviderRequest,
    P6ProviderResponse,
    P6StageEvidence,
    P6Status,
    artifact_tree_sha256,
    manifest_sha256,
    prediction_sha256,
)
from loto.adapters.gluonts.p6_registry import (
    EXPECTED_MODELS,
    get_model_spec,
    model_spec_sha256,
    registry_sha256,
)


def invocation(response: P6ProviderResponse) -> StageInvocation:
    path = Path("/tmp/fake")
    return StageInvocation(
        response=response,
        return_code=0 if response.status is P6Status.VERIFIED else 2,
        request_path=path,
        response_path=path,
        stdout_path=path,
        stderr_path=path,
        request_sha256="0" * 64,
        response_sha256="1" * 64,
    )


def verified_response(request: P6ProviderRequest) -> P6ProviderResponse:
    spec = get_model_spec(request.model_class)
    files = [ArtifactFile(relative_path="model.json", size_bytes=1, sha256="0" * 64)]
    manifest = P6PredictorManifest(
        lane=request.lane,
        model_class=request.model_class,
        distribution_output=spec.certified_distributions[0],
        fit_process_id=1000 + EXPECTED_MODELS.index(request.model_class),
        seed=1,
        freq="D",
        prediction_length=1,
        context_length=(spec.default_context_length if spec.supports_context_length else None),
        registry_sha256=registry_sha256(),
        model_spec_sha256=model_spec_sha256(spec),
        constructor_arguments_sha256="2" * 64,
        dataset_sha256="3" * 64,
        pre_reload_prediction_sha256=prediction_sha256([1.0]),
        runtime_versions={"gluonts": "0.16.3", "torch": "2.9.1"},
        files=files,
        tree_sha256=artifact_tree_sha256(files),
    )
    digest = manifest_sha256(manifest)
    if request.operation is P6Operation.FIT_SERIALIZE:
        evidence = P6StageEvidence(
            lane=request.lane,
            operation=request.operation,
            model_class=request.model_class,
            distribution_output=spec.certified_distributions[0],
            status=P6Status.VERIFIED,
            process_id=manifest.fit_process_id,
            prediction_length=1,
            expected_shape=[1],
            observed_shape=[1],
            prediction_values=[1.0],
            observed_devices=["cpu"],
            artifact_manifest=manifest,
            artifact_manifest_sha256=digest,
            checks={name: P6CheckState.PASS for name in FIT_CHECKS},
        )
    else:
        evidence = P6StageEvidence(
            lane=request.lane,
            operation=request.operation,
            model_class=request.model_class,
            distribution_output=spec.certified_distributions[0],
            status=P6Status.VERIFIED,
            process_id=2000 + EXPECTED_MODELS.index(request.model_class),
            fit_process_id=manifest.fit_process_id,
            prediction_length=1,
            expected_shape=[1],
            observed_shape=[1],
            prediction_values=[1.1],
            observed_devices=["cpu"],
            artifact_manifest_sha256=digest,
            checks={name: P6CheckState.PASS for name in LOAD_CHECKS},
        )
    return P6ProviderResponse(
        request_id=request.request_id,
        run_id=request.run_id,
        lane=request.lane,
        status=P6Status.VERIFIED,
        evidence=evidence,
    )


def fake_verified_invoker(
    request: P6ProviderRequest,
    command: Sequence[str],
    artifact_root: Path,
    timeout_seconds: float,
) -> StageInvocation:
    assert command == ["provider"]
    assert timeout_seconds == 30.0
    return invocation(verified_response(request))


def fake_blocked_invoker(
    request: P6ProviderRequest,
    command: Sequence[str],
    artifact_root: Path,
    timeout_seconds: float,
) -> StageInvocation:
    assert request.operation is P6Operation.FIT_SERIALIZE
    spec = get_model_spec(request.model_class)
    evidence = P6StageEvidence(
        lane=request.lane,
        operation=request.operation,
        model_class=request.model_class,
        distribution_output=spec.certified_distributions[0],
        status=P6Status.BLOCKED,
        process_id=1,
        prediction_length=1,
        expected_shape=[1],
        failure_category=FailureCategory.VERSION_MISMATCH,
        checks={name: P6CheckState.NOT_RUN for name in FIT_CHECKS},
        errors=["runtime missing"],
    )
    response = P6ProviderResponse(
        request_id=request.request_id,
        run_id=request.run_id,
        lane=request.lane,
        status=P6Status.BLOCKED,
        evidence=evidence,
        errors=["runtime missing"],
    )
    return invocation(response)


def test_campaign_runs_all_nine_models_with_eight_workers(tmp_path: Path) -> None:
    campaign = run_p6_campaign(
        run_id="p6-run",
        lane="compat",
        command=["provider"],
        artifact_root=tmp_path,
        workers=8,
        timeout_seconds=30.0,
        invoker=fake_verified_invoker,
    )
    assert campaign.status is P6Status.VERIFIED
    assert campaign.workers == 8
    assert tuple(model.model_class for model in campaign.models) == EXPECTED_MODELS
    assert (tmp_path / "p6_campaign_result.json").exists()
    assert (tmp_path / "p6_campaign_manifest.json").exists()


def test_campaign_does_not_start_reload_when_fit_is_blocked(tmp_path: Path) -> None:
    campaign = run_p6_campaign(
        run_id="p6-blocked",
        lane="compat",
        command=["provider"],
        artifact_root=tmp_path,
        workers=8,
        timeout_seconds=30.0,
        invoker=fake_blocked_invoker,
    )
    assert campaign.status is P6Status.BLOCKED
    assert all(model.reload is None for model in campaign.models)

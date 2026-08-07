from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from loto.adapters.gluonts.lifecycle import certify_predictor_lifecycle
from loto.adapters.gluonts.protocol import (
    DatasetItem,
    EnvironmentLane,
    GluonTSProviderRequest,
    GluonTSProviderResponse,
    ProviderOperation,
    ProviderStatus,
)
from loto.adapters.gluonts.serialization import (
    ArtifactFile,
    LifecycleCheckState,
    LifecycleOutcome,
    PredictorArtifactManifest,
    PredictorFitSerializeResult,
    PredictorReloadResult,
    artifact_tree_sha256,
    fit_result_sha256,
    manifest_sha256,
    reload_result_sha256,
)


def _manifest() -> PredictorArtifactManifest:
    files = [
        ArtifactFile(
            relative_path="model.json",
            size_bytes=2,
            sha256="1" * 64,
        )
    ]
    return PredictorArtifactManifest(
        lane="compat",
        fit_process_id=101,
        seed=1,
        freq="D",
        prediction_length=1,
        context_length=8,
        dataset_sha256="2" * 64,
        pre_reload_prediction_sha256="3" * 64,
        runtime_versions={"gluonts": "0.16.3", "torch": "2.9.1"},
        files=files,
        tree_sha256=artifact_tree_sha256(files),
    )


def _fit_result() -> PredictorFitSerializeResult:
    artifact = _manifest()
    checks = {
        name: LifecycleCheckState.PASS
        for name in (
            "version",
            "import",
            "constructor",
            "dataset",
            "fit",
            "predict",
            "shape",
            "finite",
            "device",
            "serialize",
            "artifact_integrity",
        )
    }
    return PredictorFitSerializeResult(
        lane="compat",
        outcome=LifecycleOutcome.VERIFIED,
        process_id=101,
        seed=1,
        prediction_length=1,
        context_length=8,
        expected_shape=[1],
        observed_shape=[1],
        prediction_values=[3.25],
        observed_devices=["cpu"],
        artifact_manifest=artifact,
        artifact_manifest_sha256=manifest_sha256(artifact),
        checks=checks,
    )


def _reload_result(manifest_digest: str) -> PredictorReloadResult:
    checks = {
        name: LifecycleCheckState.PASS
        for name in (
            "manifest",
            "artifact_integrity",
            "process_restart",
            "version",
            "deserialize",
            "dataset",
            "predict",
            "shape",
            "finite",
            "device",
            "identity",
        )
    }
    return PredictorReloadResult(
        lane="compat",
        outcome=LifecycleOutcome.VERIFIED,
        fit_process_id=101,
        load_process_id=202,
        prediction_length=1,
        expected_shape=[1],
        observed_shape=[1],
        prediction_values=[3.25],
        observed_devices=["cpu"],
        artifact_manifest_sha256=manifest_digest,
        checks=checks,
    )


def _request() -> GluonTSProviderRequest:
    return GluonTSProviderRequest(
        request_id="fit-1",
        run_id="run-1",
        lane=EnvironmentLane.COMPAT,
        operation=ProviderOperation.FIT_PREDICT,
        model_class="DeepAREstimator",
        dataset=[
            DatasetItem(
                item_id="series-1",
                start="2000-01-01",
                target=[1.0, 2.0, 3.0],
            )
        ],
    )


def test_lifecycle_uses_two_provider_invocations(tmp_path: Path) -> None:
    fit = _fit_result()
    reload = _reload_result(fit.artifact_manifest_sha256)
    calls: list[ProviderOperation] = []

    def invoke(request, command, artifact_root, timeout_seconds):
        calls.append(request.operation)
        if request.operation is ProviderOperation.FIT_PREDICT:
            response = GluonTSProviderResponse(
                request_id=request.request_id,
                run_id=request.run_id,
                lane=request.lane,
                status=ProviderStatus.PARTIALLY_VERIFIED,
                metadata={
                    "predictor_fit_serialize": fit.model_dump(mode="json"),
                    "predictor_fit_serialize_sha256": fit_result_sha256(fit),
                },
            )
            return SimpleNamespace(
                response=response,
                response_sha256="4" * 64,
                return_code=0,
            )
        response = GluonTSProviderResponse(
            request_id=request.request_id,
            run_id=request.run_id,
            lane=request.lane,
            status=ProviderStatus.PARTIALLY_VERIFIED,
            metadata={
                "predictor_reload": reload.model_dump(mode="json"),
                "predictor_reload_sha256": reload_result_sha256(reload),
            },
        )
        return SimpleNamespace(
            response=response,
            response_sha256="5" * 64,
            return_code=0,
        )

    result = certify_predictor_lifecycle(
        _request(),
        ["provider"],
        tmp_path / "artifacts",
        tmp_path / "predictor",
        invoke=invoke,
    )

    assert calls == [
        ProviderOperation.FIT_PREDICT,
        ProviderOperation.LOAD_PREDICT,
    ]
    assert result.result.outcome is LifecycleOutcome.VERIFIED
    assert result.result.reload is not None
    assert result.result.fit.process_id == 101
    assert result.result.reload.load_process_id == 202
    assert result.result_path.exists()
    assert result.manifest_path.exists()


def test_lifecycle_stops_after_blocked_fit(tmp_path: Path) -> None:
    verified = _fit_result()
    fit = verified.model_copy(
        update={
            "outcome": LifecycleOutcome.BLOCKED,
            "artifact_manifest": None,
            "artifact_manifest_sha256": None,
            "errors": ["runtime packages unavailable"],
            "checks": {
                name: (
                    LifecycleCheckState.BLOCKED
                    if name == "version"
                    else LifecycleCheckState.NOT_RUN
                )
                for name in verified.checks
            },
        }
    )
    calls: list[ProviderOperation] = []

    def invoke(request, command, artifact_root, timeout_seconds):
        calls.append(request.operation)
        response = GluonTSProviderResponse(
            request_id=request.request_id,
            run_id=request.run_id,
            lane=request.lane,
            status=ProviderStatus.EXECUTION_PENDING,
            metadata={
                "predictor_fit_serialize": fit.model_dump(mode="json"),
                "predictor_fit_serialize_sha256": fit_result_sha256(fit),
            },
        )
        return SimpleNamespace(
            response=response,
            response_sha256="6" * 64,
            return_code=0,
        )

    result = certify_predictor_lifecycle(
        _request(),
        ["provider"],
        tmp_path / "artifacts",
        tmp_path / "predictor",
        invoke=invoke,
    )
    assert calls == [ProviderOperation.FIT_PREDICT]
    assert result.result.outcome is LifecycleOutcome.BLOCKED
    assert result.result.reload is None

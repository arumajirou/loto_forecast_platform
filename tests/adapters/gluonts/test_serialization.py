from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from loto.adapters.gluonts.serialization import (
    ArtifactFile,
    LifecycleCheckState,
    LifecycleOutcome,
    PredictorArtifactManifest,
    PredictorFitSerializeResult,
    PredictorLifecycleResult,
    PredictorReloadResult,
    artifact_tree_sha256,
    manifest_sha256,
)


def artifact_manifest() -> PredictorArtifactManifest:
    files = [
        ArtifactFile(
            relative_path="model.json",
            size_bytes=12,
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


def fit_checks() -> dict[str, LifecycleCheckState]:
    return {
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


def reload_checks() -> dict[str, LifecycleCheckState]:
    return {
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


def verified_fit() -> PredictorFitSerializeResult:
    manifest = artifact_manifest()
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
        artifact_manifest=manifest,
        artifact_manifest_sha256=manifest_sha256(manifest),
        checks=fit_checks(),
    )


def verified_reload(manifest_digest: str) -> PredictorReloadResult:
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
        checks=reload_checks(),
    )


def test_manifest_rejects_tree_hash_mismatch() -> None:
    with pytest.raises(ValidationError, match="tree SHA-256"):
        PredictorArtifactManifest(
            lane="compat",
            fit_process_id=101,
            seed=1,
            freq="D",
            prediction_length=1,
            context_length=8,
            dataset_sha256="2" * 64,
            pre_reload_prediction_sha256="3" * 64,
            files=[
                ArtifactFile(
                    relative_path="model.json",
                    size_bytes=12,
                    sha256="1" * 64,
                )
            ],
            tree_sha256="0" * 64,
        )


def test_verified_fit_requires_serialize_pass() -> None:
    manifest = artifact_manifest()
    checks = fit_checks()
    checks["serialize"] = LifecycleCheckState.FAIL
    with pytest.raises(ValidationError, match="every check"):
        PredictorFitSerializeResult(
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
            artifact_manifest=manifest,
            artifact_manifest_sha256=manifest_sha256(manifest),
            checks=checks,
        )


def test_verified_reload_requires_new_process() -> None:
    digest = manifest_sha256(artifact_manifest())
    with pytest.raises(ValidationError, match="new process"):
        PredictorReloadResult(
            lane="compat",
            outcome=LifecycleOutcome.VERIFIED,
            fit_process_id=101,
            load_process_id=101,
            prediction_length=1,
            expected_shape=[1],
            observed_shape=[1],
            prediction_values=[3.25],
            observed_devices=["cpu"],
            artifact_manifest_sha256=digest,
            checks=reload_checks(),
        )


def test_lifecycle_requires_same_manifest_identity() -> None:
    fit = verified_fit()
    reload = verified_reload("4" * 64)
    with pytest.raises(ValidationError, match="reload manifest identity"):
        PredictorLifecycleResult(
            lane="compat",
            outcome=LifecycleOutcome.VERIFIED,
            fit_request_id="fit-1",
            load_request_id="load-1",
            fit=fit,
            reload=reload,
            artifact_manifest_sha256=fit.artifact_manifest_sha256,
        )


def test_non_finite_reload_prediction_is_rejected() -> None:
    with pytest.raises(ValidationError, match="finite"):
        PredictorReloadResult(
            lane="compat",
            outcome=LifecycleOutcome.FAILED,
            fit_process_id=101,
            load_process_id=202,
            prediction_length=1,
            expected_shape=[1],
            prediction_values=[math.inf],
            artifact_manifest_sha256="4" * 64,
            checks={
                name: LifecycleCheckState.FAIL
                for name in reload_checks()
            },
            errors=["non-finite"],
        )

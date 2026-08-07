from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Callable

from .p6_contract import (
    LOAD_CHECKS,
    FailureCategory,
    P6CheckState,
    P6ProviderRequest,
    P6StageEvidence,
    P6Status,
    prediction_sha256,
    sha256_json,
)
from .p6_registry import get_model_spec, model_spec_sha256, registry_sha256
from .p6_runtime_common import (
    RuntimeBindings,
    _checks,
    _dataset,
    _devices,
    _failure,
    _forecast,
    load_runtime_bindings,
    runtime_versions,
    verify_artifact_directory,
    version_matches,
)


def load_predict(
    request: P6ProviderRequest,
    *,
    bindings_loader: Callable[[], RuntimeBindings] = load_runtime_bindings,
    observed_versions: dict[str, str | None] | None = None,
) -> P6StageEvidence:
    checks = _checks(LOAD_CHECKS)
    artifact_dir = Path(request.artifact_dir).resolve()
    fit_pid = 1
    manifest_digest = None
    distribution_name = request.distribution_output or "UNRESOLVED"
    try:
        manifest, manifest_digest = verify_artifact_directory(artifact_dir)
        fit_pid = manifest.fit_process_id
        distribution_name = manifest.distribution_output
        checks["manifest"] = P6CheckState.PASS
        checks["artifact_integrity"] = P6CheckState.PASS
    except Exception as exc:
        checks["manifest"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.ARTIFACT_INTEGRITY_FAILED,
            f"{type(exc).__name__}: {exc}",
            fit_process_id=fit_pid,
            distribution_output=distribution_name,
        )
    try:
        spec = get_model_spec(manifest.model_class)
        checks["registry"] = P6CheckState.PASS
    except KeyError:
        checks["registry"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.MODEL_UNSUPPORTED,
            f"manifest model is not in registry: {manifest.model_class}",
            fit_process_id=fit_pid,
            manifest_sha=manifest_digest,
            distribution_output=distribution_name,
        )
    request_distribution = request.distribution_output or manifest.distribution_output
    identity_matches = (
        manifest.model_class == request.model_class
        and manifest.lane == request.lane
        and manifest.distribution_output == request_distribution
        and manifest.prediction_length == request.prediction_length
        and manifest.freq == request.freq
        and (
            not spec.supports_context_length
            or manifest.context_length
            == (request.context_length or spec.default_context_length)
        )
    )
    if not identity_matches:
        checks["identity"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.IDENTITY_MISMATCH,
            "request, lane, and predictor manifest identity mismatch",
            fit_process_id=fit_pid,
            manifest_sha=manifest_digest,
            distribution_output=distribution_name,
        )
    if manifest.registry_sha256 != registry_sha256() or (
        manifest.model_spec_sha256 != model_spec_sha256(spec)
    ):
        checks["identity"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.IDENTITY_MISMATCH,
            "registry or model specification identity mismatch",
            fit_process_id=fit_pid,
            manifest_sha=manifest_digest,
            distribution_output=distribution_name,
        )
    if os.getpid() == fit_pid:
        checks["process_restart"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.PROCESS_RESTART_REQUIRED,
            "load_predict must execute in a new provider process",
            fit_process_id=fit_pid,
            manifest_sha=manifest_digest,
            distribution_output=distribution_name,
        )
    checks["process_restart"] = P6CheckState.PASS
    versions = observed_versions or runtime_versions()
    valid, reason = version_matches(request.lane, versions)
    if not valid:
        checks["version"] = P6CheckState.BLOCKED
        return _failure(
            request,
            checks,
            FailureCategory.VERSION_MISMATCH,
            reason,
            status=P6Status.BLOCKED,
            fit_process_id=fit_pid,
            manifest_sha=manifest_digest,
            distribution_output=distribution_name,
        )
    if versions != manifest.runtime_versions:
        checks["version"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.IDENTITY_MISMATCH,
            "runtime version identity changed between fit and reload",
            fit_process_id=fit_pid,
            manifest_sha=manifest_digest,
            distribution_output=distribution_name,
        )
    checks["version"] = P6CheckState.PASS
    try:
        runtime = bindings_loader()
        predictor = runtime.predictor_class.deserialize(artifact_dir)
        checks["deserialize"] = P6CheckState.PASS
    except Exception as exc:
        checks["deserialize"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.DESERIALIZE_FAILED,
            f"{type(exc).__name__}: {exc}",
            fit_process_id=fit_pid,
            manifest_sha=manifest_digest,
            distribution_output=distribution_name,
        )
    try:
        dataset_document = __import__("json").loads(
            (artifact_dir / "p6_certification_dataset.json").read_text("utf-8")
        )
        if sha256_json(dataset_document) != manifest.dataset_sha256:
            raise ValueError("stored certification dataset SHA-256 mismatch")
        dataset = _dataset(dataset_document["dataset"], dataset_document["freq"], runtime)
        checks["dataset"] = P6CheckState.PASS
    except Exception as exc:
        checks["dataset"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.DATASET_FAILED,
            f"{type(exc).__name__}: {exc}",
            fit_process_id=fit_pid,
            manifest_sha=manifest_digest,
            distribution_output=distribution_name,
        )
    try:
        values = _forecast(predictor, dataset, runtime)
        checks["predict"] = P6CheckState.PASS
    except Exception as exc:
        checks["predict"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.PREDICT_FAILED,
            f"{type(exc).__name__}: {exc}",
            fit_process_id=fit_pid,
            manifest_sha=manifest_digest,
            distribution_output=distribution_name,
        )
    observed_shape = [len(values)]
    if observed_shape != [manifest.prediction_length]:
        checks["shape"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.OUTPUT_SHAPE_FAILED,
            f"observed shape {observed_shape} does not match manifest",
            fit_process_id=fit_pid,
            manifest_sha=manifest_digest,
            distribution_output=distribution_name,
        )
    checks["shape"] = P6CheckState.PASS
    if not all(math.isfinite(value) for value in values):
        checks["finite"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.NON_FINITE_OUTPUT,
            "reload prediction contains non-finite values",
            fit_process_id=fit_pid,
            manifest_sha=manifest_digest,
            distribution_output=distribution_name,
        )
    checks["finite"] = P6CheckState.PASS
    devices = _devices(predictor)
    if not devices or any(not device.startswith("cpu") for device in devices):
        checks["device"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.DEVICE_MISMATCH,
            f"expected observed CPU parameters, got {devices}",
            fit_process_id=fit_pid,
            manifest_sha=manifest_digest,
            distribution_output=distribution_name,
        )
    checks["device"] = P6CheckState.PASS
    checks["identity"] = P6CheckState.PASS
    return P6StageEvidence(
        lane=request.lane,
        operation=request.operation,
        model_class=request.model_class,
        distribution_output=distribution_name,
        status=P6Status.VERIFIED,
        process_id=os.getpid(),
        fit_process_id=fit_pid,
        prediction_length=manifest.prediction_length,
        expected_shape=[manifest.prediction_length],
        observed_shape=observed_shape,
        prediction_values=values,
        observed_devices=devices,
        artifact_manifest_sha256=manifest_digest,
        checks=checks,
        metadata={
            "post_reload_prediction_sha256": prediction_sha256(values),
            "pre_reload_prediction_sha256": manifest.pre_reload_prediction_sha256,
            "runtime_versions": versions,
        },
    )

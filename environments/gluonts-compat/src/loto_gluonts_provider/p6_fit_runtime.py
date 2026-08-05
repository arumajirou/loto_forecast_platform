from __future__ import annotations

import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from .p6_contract import (
    FIT_CHECKS,
    FailureCategory,
    P6CheckState,
    P6PredictorManifest,
    P6ProviderRequest,
    P6StageEvidence,
    P6Status,
    artifact_tree_sha256,
    atomic_write_json,
    manifest_sha256,
    prediction_sha256,
    sha256_json,
)
from .p6_registry import get_model_spec, model_spec_sha256, registry_sha256
from .p6_runtime_common import (
    RuntimeBindings,
    _checks,
    _dataset,
    _dataset_payload,
    _devices,
    _failure,
    _default_distribution,
    _forecast,
    _resolve_distribution,
    _seed,
    collect_artifact_files,
    constructor_arguments,
    load_runtime_bindings,
    runtime_versions,
    validate_signature,
    verify_artifact_directory,
    version_matches,
)


def fit_serialize(
    request: P6ProviderRequest,
    *,
    bindings_loader: Callable[[], RuntimeBindings] = load_runtime_bindings,
    observed_versions: dict[str, str | None] | None = None,
) -> P6StageEvidence:
    checks = _checks(FIT_CHECKS)
    try:
        spec = get_model_spec(request.model_class)
        checks["registry"] = P6CheckState.PASS
    except KeyError:
        checks["registry"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.MODEL_UNSUPPORTED,
            f"unsupported P6 model: {request.model_class}",
        )
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
            distribution_output=_default_distribution(spec),
        )
    checks["version"] = P6CheckState.PASS
    try:
        runtime = bindings_loader()
        estimator_class = runtime.estimators[request.model_class]
        checks["import"] = P6CheckState.PASS
    except Exception as exc:
        checks["import"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.IMPORT_FAILED,
            f"{type(exc).__name__}: {exc}",
            distribution_output=_default_distribution(spec),
        )
    try:
        distribution_name, distribution = _resolve_distribution(request, spec, runtime)
    except Exception as exc:
        return _failure(
            request,
            checks,
            FailureCategory.DISTRIBUTION_UNSUPPORTED,
            f"{type(exc).__name__}: {exc}",
            distribution_output=request.distribution_output or "UNRESOLVED",
        )
    try:
        arguments = constructor_arguments(request, spec, distribution)
        checks["resource_policy"] = P6CheckState.PASS
    except KeyError as exc:
        checks["resource_policy"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.UNSUPPORTED_ARGUMENT,
            str(exc),
            distribution_output=distribution_name,
        )
    except Exception as exc:
        checks["resource_policy"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.RESOURCE_POLICY_VIOLATION,
            f"{type(exc).__name__}: {exc}",
            distribution_output=distribution_name,
        )
    try:
        signature = validate_signature(estimator_class, spec, arguments)
        checks["signature"] = P6CheckState.PASS
    except Exception as exc:
        checks["signature"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.SIGNATURE_MISMATCH,
            f"{type(exc).__name__}: {exc}",
            distribution_output=distribution_name,
        )
    try:
        _seed(runtime, request.seed)
        estimator = estimator_class(**arguments)
        checks["constructor"] = P6CheckState.PASS
    except Exception as exc:
        checks["constructor"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.CONSTRUCTOR_FAILED,
            f"{type(exc).__name__}: {exc}",
            distribution_output=distribution_name,
        )
    payload = _dataset_payload(request.dataset)
    if len(payload[0]["target"]) < spec.min_target_length:
        checks["dataset"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.DATASET_FAILED,
            f"target length must be at least {spec.min_target_length}",
            distribution_output=distribution_name,
        )
    try:
        dataset = _dataset(payload, request.freq, runtime)
        checks["dataset"] = P6CheckState.PASS
    except Exception as exc:
        checks["dataset"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.DATASET_FAILED,
            f"{type(exc).__name__}: {exc}",
            distribution_output=distribution_name,
        )
    try:
        predictor = estimator.train(training_data=dataset)
        checks["fit"] = P6CheckState.PASS
    except Exception as exc:
        checks["fit"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.FIT_FAILED,
            f"{type(exc).__name__}: {exc}",
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
            distribution_output=distribution_name,
        )
    observed_shape = [len(values)]
    if observed_shape != [request.prediction_length]:
        checks["shape"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.OUTPUT_SHAPE_FAILED,
            f"observed shape {observed_shape} does not match prediction length",
            distribution_output=distribution_name,
        )
    checks["shape"] = P6CheckState.PASS
    if not all(math.isfinite(value) for value in values):
        checks["finite"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.NON_FINITE_OUTPUT,
            "prediction contains non-finite values",
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
            distribution_output=distribution_name,
        )
    checks["device"] = P6CheckState.PASS

    final = Path(request.artifact_dir).resolve()
    if final.exists() and any(final.iterdir()):
        checks["serialize"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.SERIALIZE_FAILED,
            "predictor artifact directory must be absent or empty",
            distribution_output=distribution_name,
        )
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists():
        final.rmdir()
    staging = Path(tempfile.mkdtemp(prefix=f".{final.name}.staging-", dir=final.parent))
    try:
        predictor.serialize(staging)
        checks["serialize"] = P6CheckState.PASS
        dataset_document = {
            "schema_version": 1,
            "freq": request.freq,
            "dataset": payload,
        }
        constructor_document = {
            "schema_version": 1,
            "model_class": request.model_class,
            "signature": signature,
            "arguments": {
                key: value
                for key, value in arguments.items()
                if key not in {"distr_output"}
            },
            "distribution_output": distribution_name,
        }
        atomic_write_json(staging / "p6_certification_dataset.json", dataset_document)
        atomic_write_json(staging / "p6_constructor_arguments.json", constructor_document)
        files = collect_artifact_files(staging)
        manifest = P6PredictorManifest(
            lane=request.lane,
            model_class=request.model_class,
            distribution_output=distribution_name,
            fit_process_id=os.getpid(),
            seed=request.seed,
            freq=request.freq,
            prediction_length=request.prediction_length,
            context_length=(
                request.context_length or spec.default_context_length
                if spec.supports_context_length
                else None
            ),
            registry_sha256=registry_sha256(),
            model_spec_sha256=model_spec_sha256(spec),
            constructor_arguments_sha256=sha256_json(constructor_document),
            dataset_sha256=sha256_json(dataset_document),
            pre_reload_prediction_sha256=prediction_sha256(values),
            runtime_versions=versions,
            files=files,
            tree_sha256=artifact_tree_sha256(files),
        )
        manifest_digest = atomic_write_json(
            staging / "p6_predictor_manifest.json",
            manifest.model_dump(mode="json"),
        )
        verified, verified_sha = verify_artifact_directory(staging)
        if verified != manifest or verified_sha != manifest_digest:
            raise ValueError("serialized predictor manifest verification mismatch")
        checks["artifact_integrity"] = P6CheckState.PASS
        os.replace(staging, final)
    except Exception as exc:
        checks["artifact_integrity"] = P6CheckState.FAIL
        return _failure(
            request,
            checks,
            FailureCategory.ARTIFACT_INTEGRITY_FAILED,
            f"{type(exc).__name__}: {exc}",
            distribution_output=distribution_name,
        )
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    return P6StageEvidence(
        lane=request.lane,
        operation=request.operation,
        model_class=request.model_class,
        distribution_output=distribution_name,
        status=P6Status.VERIFIED,
        process_id=os.getpid(),
        prediction_length=request.prediction_length,
        expected_shape=[request.prediction_length],
        observed_shape=observed_shape,
        prediction_values=values,
        observed_devices=devices,
        artifact_manifest=manifest,
        artifact_manifest_sha256=manifest_digest,
        checks=checks,
        metadata={
            "constructor_signature": signature,
            "constructor_arguments_sha256": manifest.constructor_arguments_sha256,
            "runtime_versions": versions,
        },
    )

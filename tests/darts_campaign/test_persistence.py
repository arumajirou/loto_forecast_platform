from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from loto.darts_campaign.persistence import (
    P11_FAMILIES,
    ArtifactEvidence,
    ModelSnapshot,
    PersistenceCampaignConfig,
    PersistenceContractError,
    PersistenceEvidence,
    PersistenceSpec,
    PersistenceTask,
    TemporalPrediction,
    build_persistence_tasks,
    canonical_sha256,
    certify_persistence,
    classify_arguments,
    run_persistence_matrix,
)
from loto.darts_campaign.torch_models import TorchRuntimeObservation


def specs() -> tuple[PersistenceSpec, ...]:
    return (
        PersistenceSpec(
            model_id="local-naive",
            family="local",
            public_name="NaiveDrift",
            methods=("manual",),
        ),
        PersistenceSpec(
            model_id="reg-linear",
            family="regression",
            public_name="LinearRegressionModel",
            supports_clean=True,
            methods=("manual", "manual_clean"),
        ),
        PersistenceSpec(
            model_id="torch-tft",
            family="torch",
            public_name="TFTModel",
            torch_backed=True,
            supports_clean=True,
            supports_checkpoint=True,
            supports_weights=True,
            requested_accelerator="gpu",
            device_index=0,
            methods=(
                "manual",
                "manual_clean",
                "checkpoint_best",
                "checkpoint_last",
                "weights",
                "cross_device_cpu",
                "cross_device_cuda",
            ),
        ),
        PersistenceSpec(
            model_id="foundation-chronos",
            family="foundation",
            public_name="Chronos2Model",
            torch_backed=True,
            supports_clean=True,
            supports_checkpoint=True,
            supports_weights=True,
            requested_accelerator="gpu",
            device_index=0,
            methods=(
                "manual",
                "manual_clean",
                "checkpoint_best",
                "checkpoint_last",
                "weights",
                "cross_device_cpu",
                "cross_device_cuda",
            ),
        ),
        PersistenceSpec(
            model_id="ensemble-reg",
            family="ensemble",
            public_name="RegressionEnsembleModel",
            supports_clean=True,
            methods=("manual", "manual_clean"),
        ),
        PersistenceSpec(
            model_id="conformal-naive",
            family="conformal",
            public_name="ConformalNaiveModel",
            supports_clean=True,
            methods=("manual", "manual_clean"),
        ),
    )


def campaign() -> PersistenceCampaignConfig:
    return PersistenceCampaignConfig(run_id="darts-p11", specs=specs())


def gpu_observation(pid: int = 200) -> TorchRuntimeObservation:
    return TorchRuntimeObservation(
        torch_cuda_available=True,
        requested_accelerator="gpu",
        effective_accelerator="gpu",
        model_parameter_devices=("cuda:0",),
        prediction_device="cuda:0",
        process_pid=pid,
        gpu_pid=pid,
        device_index=0,
        vram_before_bytes=100,
        vram_peak_bytes=300,
        vram_after_bytes=120,
        cuda_allocated_bytes=80,
        cuda_reserved_bytes=100,
    )


def cpu_observation(pid: int = 201) -> TorchRuntimeObservation:
    return TorchRuntimeObservation(
        torch_cuda_available=True,
        requested_accelerator="cpu",
        effective_accelerator="cpu",
        model_parameter_devices=("cpu",),
        prediction_device="cpu",
        process_pid=pid,
    )


def artifact(path: str, token: str = "artifact") -> ArtifactEvidence:
    digest = canonical_sha256({"token": token, "path": path})
    return ArtifactEvidence(
        path=path,
        size_bytes_at_save=128,
        size_bytes_at_load=128,
        sha256_at_save=digest,
        sha256_at_load=digest,
    )


def evidence(spec: PersistenceSpec, method: str) -> PersistenceEvidence:
    task = PersistenceTask(
        model_id=spec.model_id,
        family=spec.family,
        public_name=spec.public_name,
        method=method,
    )
    clean = method == "manual_clean"
    before = ModelSnapshot(
        model_id=spec.model_id,
        family=spec.family,
        public_name=spec.public_name,
        class_path=f"darts.models.{spec.public_name}",
        parameters_sha256=canonical_sha256({"model": spec.model_id}),
        fitted=True,
        training_state_present=True,
        covariate_state_present=True,
    )
    after = before.model_copy(
        update={
            "training_state_present": not clean,
            "covariate_state_present": not clean,
        }
    )
    files = [artifact(f"artifacts/{spec.model_id}.pkl")]
    if spec.torch_backed:
        if method == "checkpoint_best":
            files = [artifact(f"checkpoints/best-{spec.model_id}.ckpt")]
        elif method == "checkpoint_last":
            files = [artifact(f"checkpoints/last-{spec.model_id}.ckpt")]
        else:
            files = [
                artifact(f"artifacts/{spec.model_id}.pt"),
                artifact(f"artifacts/{spec.model_id}.pt.ckpt"),
            ]
    before_device = None
    after_device = None
    map_location = None
    if spec.torch_backed:
        before_device = gpu_observation(100)
        after_device = gpu_observation(200)
        if method == "cross_device_cpu":
            map_location = "cpu"
            after_device = cpu_observation(200)
        elif method == "cross_device_cuda":
            map_location = "cuda:0"
            before_device = cpu_observation(100)
            after_device = gpu_observation(200)
    checkpoint_kind = None
    trainer = optimizer = scheduler = None
    if method == "checkpoint_best":
        checkpoint_kind = "best"
        trainer = optimizer = scheduler = True
    elif method == "checkpoint_last":
        checkpoint_kind = "last"
        trainer = optimizer = scheduler = True
    initialized = weights_loaded = encoders_loaded = None
    if method == "weights":
        initialized = weights_loaded = encoders_loaded = True
    prediction = TemporalPrediction(values=((1.0, 2.0), (3.0, 4.0)))
    return PersistenceEvidence(
        task=task,
        save_process_pid=100,
        load_process_pid=200,
        save_process_ended=True,
        loaded_from_disk=True,
        object_identity_reused=False,
        artifacts=tuple(files),
        before_snapshot=before,
        after_snapshot=after,
        prediction_before=prediction,
        prediction_after=prediction,
        clean_requested=clean,
        requested_map_location=map_location,
        checkpoint_kind=checkpoint_kind,
        trainer_state_restored=trainer,
        optimizer_state_restored=optimizer,
        scheduler_state_restored=scheduler,
        model_initialized_before_weights=initialized,
        weights_loaded=weights_loaded,
        encoders_loaded=encoders_loaded,
        device_before=before_device,
        device_after=after_device,
    )


def test_campaign_requires_exact_six_family_coverage() -> None:
    config = campaign()
    assert tuple(spec.family for spec in config.specs) == P11_FAMILIES
    with pytest.raises(ValidationError):
        PersistenceCampaignConfig(run_id="bad", specs=specs()[:-1])


def test_method_capabilities_are_fail_closed() -> None:
    with pytest.raises(ValidationError, match="manual_clean"):
        PersistenceSpec(
            model_id="local",
            family="local",
            public_name="NaiveDrift",
            methods=("manual", "manual_clean"),
        )
    with pytest.raises(ValidationError, match="checkpoint"):
        PersistenceSpec(
            model_id="reg",
            family="regression",
            public_name="LinearRegressionModel",
            methods=("manual", "checkpoint_best"),
        )


def test_persistence_arguments_cannot_be_silently_dropped() -> None:
    def load(path: str, map_location: str | None = None) -> None:
        del path, map_location

    effective, ledger = classify_arguments(
        load,
        {"path": "model.pt", "map_location": "cpu"},
        target_name="TorchForecastingModel.load",
    )
    assert effective == {"path": "model.pt", "map_location": "cpu"}
    assert all(item.status == "accepted" for item in ledger)
    with pytest.raises(PersistenceContractError, match="unknown"):
        classify_arguments(
            load,
            {"path": "model.pt", "unknown": 1},
            target_name="TorchForecastingModel.load",
        )


def test_manual_roundtrip_certifies_non_torch_family() -> None:
    spec = specs()[0]
    report = certify_persistence(spec, evidence(spec, "manual"))
    assert report.status == "PERSISTENCE_CERTIFIED"
    assert all(check.passed for check in report.checks)


def test_process_boundary_is_mandatory() -> None:
    spec = specs()[0]
    current = evidence(spec, "manual")
    broken = current.model_copy(update={"load_process_pid": 100})
    report = certify_persistence(spec, broken)
    assert report.status == "FAILED"
    failed = {check.failure_class for check in report.checks if not check.passed}
    assert "PROCESS_BOUNDARY_MISSING" in failed


def test_artifact_manifest_detects_tamper() -> None:
    spec = specs()[0]
    current = evidence(spec, "manual")
    artifact_record = current.artifacts[0].model_copy(update={"sha256_at_load": "b" * 64})
    report = certify_persistence(
        spec,
        current.model_copy(update={"artifacts": (artifact_record,)}),
    )
    assert report.status == "FAILED"
    assert any(check.failure_class == "ARTIFACT_INTEGRITY_MISMATCH" for check in report.checks)


def test_prediction_replay_shape_and_values_are_certified() -> None:
    spec = specs()[0]
    current = evidence(spec, "manual")
    changed = current.prediction_after.model_copy(update={"values": ((1.0, 2.0), (3.0, 9.0))})
    report = certify_persistence(
        spec,
        current.model_copy(update={"prediction_after": changed}),
    )
    assert report.status == "FAILED"
    assert any(check.failure_class == "PREDICTION_REPLAY_MISMATCH" for check in report.checks)


def test_clean_save_removes_global_training_and_covariate_state() -> None:
    spec = specs()[1]
    report = certify_persistence(spec, evidence(spec, "manual_clean"))
    assert report.status == "PERSISTENCE_CERTIFIED"
    broken = evidence(spec, "manual_clean")
    after = broken.after_snapshot.model_copy(update={"training_state_present": True})
    report = certify_persistence(
        spec,
        broken.model_copy(update={"after_snapshot": after}),
    )
    assert report.status == "FAILED"
    assert any(check.failure_class == "CLEAN_SAVE_CONTRACT_FAILED" for check in report.checks)


def test_torch_manual_requires_weight_companion_and_gpu_evidence() -> None:
    spec = specs()[2]
    report = certify_persistence(spec, evidence(spec, "manual"))
    assert report.status == "PERSISTENCE_CERTIFIED"
    current = evidence(spec, "manual")
    report = certify_persistence(
        spec,
        current.model_copy(update={"artifacts": current.artifacts[:1]}),
    )
    assert report.status == "FAILED"
    assert any(check.failure_class == "TORCH_WEIGHT_ARTIFACT_MISSING" for check in report.checks)


def test_checkpoint_best_and_last_restore_training_state() -> None:
    spec = specs()[2]
    for method in ("checkpoint_best", "checkpoint_last"):
        report = certify_persistence(spec, evidence(spec, method))
        assert report.status == "PERSISTENCE_CERTIFIED"
    current = evidence(spec, "checkpoint_best")
    report = certify_persistence(
        spec,
        current.model_copy(update={"optimizer_state_restored": False}),
    )
    assert report.status == "FAILED"
    assert any(check.failure_class == "CHECKPOINT_RESTORE_INCOMPLETE" for check in report.checks)


def test_load_weights_requires_initialized_model_weights_and_encoders() -> None:
    spec = specs()[2]
    report = certify_persistence(spec, evidence(spec, "weights"))
    assert report.status == "PERSISTENCE_CERTIFIED"
    current = evidence(spec, "weights")
    report = certify_persistence(
        spec,
        current.model_copy(update={"encoders_loaded": False}),
    )
    assert report.status == "FAILED"
    assert any(check.failure_class == "WEIGHTS_RESTORE_INCOMPLETE" for check in report.checks)


def test_cross_device_cpu_and_cuda_reject_cpu_fallback() -> None:
    spec = specs()[2]
    cpu_report = certify_persistence(spec, evidence(spec, "cross_device_cpu"))
    assert cpu_report.status == "PERSISTENCE_CERTIFIED"
    cuda_report = certify_persistence(spec, evidence(spec, "cross_device_cuda"))
    assert cuda_report.status == "PERSISTENCE_CERTIFIED"
    current = evidence(spec, "cross_device_cuda")
    fallback = TorchRuntimeObservation(
        torch_cuda_available=True,
        requested_accelerator="gpu",
        effective_accelerator="cpu",
        model_parameter_devices=("cpu",),
        prediction_device="cpu",
        process_pid=200,
        cpu_fallback_reason="CUDA allocation failed",
    )
    report = certify_persistence(
        spec,
        current.model_copy(update={"device_after": fallback}),
    )
    assert report.status == "FAILED"
    assert any(check.failure_class == "DEVICE_CERTIFICATION_FAILED" for check in report.checks)


def test_matrix_retains_failure_and_continues_all_tasks() -> None:
    config = campaign()

    @dataclass
    class Runtime:
        def execute(self, task, spec):
            if task.model_id == "ensemble-reg" and task.method == "manual":
                raise RuntimeError("simulated save failure")
            return evidence(spec, task.method)

    tasks = build_persistence_tasks(config)
    results = run_persistence_matrix(config, Runtime())
    assert len(results) == len(tasks)
    failures = [result for result in results if result.status == "FAILED"]
    assert len(failures) == 1
    assert failures[0].failure_class == "RuntimeError"
    assert any(result.status == "CERTIFIED" for result in results[1:])

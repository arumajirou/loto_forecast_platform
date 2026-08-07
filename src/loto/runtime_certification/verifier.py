"""Fail-closed provider-neutral runtime-certification report builder."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .contracts import (
    CertificationReport,
    CommandSpec,
    DeviceEvidence,
    ModelIdentity,
    OutputContract,
    PackageIdentity,
    ProcessExecution,
    RequestIdentity,
    RuntimeCheckSummary,
    SnapshotIdentity,
)
from .device_evidence import validate_device_evidence
from .identity import (
    verify_package_identity,
    verify_request_identity,
    verify_snapshot_identity,
)
from .output_validation import validate_output
from .replay import compare_replay
from .statuses import AccuracyStatus, CertificationProfile, EvidenceOrigin, RuntimeStatus
from .subprocess_runner import Executor


@dataclass(frozen=True)
class RunObservation:
    execution: ProcessExecution
    output: object
    device: DeviceEvidence
    load_success: bool = True
    input_validation_success: bool = True
    inference_success: bool = True
    save_succeeded: bool = True
    reload_succeeded: bool = True
    re_predict_succeeded: bool = True


ObservationLoader = Callable[[str, ProcessExecution], RunObservation]


class CertificationVerificationError(RuntimeError):
    pass


def _validate_process_binding(
    observation: RunObservation,
    *,
    evidence_origin: EvidenceOrigin,
) -> None:
    process_pid = observation.execution.process_pid
    if evidence_origin == EvidenceOrigin.REAL and process_pid is None:
        raise CertificationVerificationError("real evidence requires an observed process PID")
    if process_pid is not None and process_pid != observation.device.provider_pid:
        raise CertificationVerificationError(
            "execution process PID differs from device provider PID"
        )
    if evidence_origin == EvidenceOrigin.REAL:
        process_identity = observation.execution.process_identity_sha256
        if process_identity is None:
            raise CertificationVerificationError(
                "real evidence requires an executor-owned process identity"
            )
        if process_identity != observation.device.provider_process_identity_sha256:
            raise CertificationVerificationError(
                "execution process identity differs from device provider identity"
            )
        if observation.device.requested_device == "cuda":
            matching_samples = [
                sample
                for sample in observation.device.external_gpu_samples
                if sample.provider_pid == process_pid
                and sample.provider_process_identity_sha256 == process_identity
                and observation.execution.started_at_utc
                <= sample.observed_at_utc
                <= observation.execution.finished_at_utc
            ]
            if not matching_samples:
                raise CertificationVerificationError(
                    "real CUDA evidence requires a process-bound sample during execution"
                )


def build_certification_report(
    *,
    certification_id: str,
    profile: CertificationProfile,
    evidence_origin: EvidenceOrigin,
    request: RequestIdentity,
    package: PackageIdentity,
    model: ModelIdentity,
    snapshot: SnapshotIdentity,
    output_contract: OutputContract,
    first: RunObservation,
    second: RunObservation,
    replay_tolerance: float = 0.0,
) -> CertificationReport:
    if first.device.origin != evidence_origin or second.device.origin != evidence_origin:
        raise CertificationVerificationError("observation origin differs from report origin")
    for observation in (first, second):
        if observation.execution.timed_out:
            raise CertificationVerificationError("process timed out")
        if observation.execution.exit_code != 0:
            raise CertificationVerificationError("provider process exit was not zero")
        _validate_process_binding(observation, evidence_origin=evidence_origin)
        validate_device_evidence(observation.device, profile=profile)
    first_output = validate_output(first.output, output_contract)
    second_output = validate_output(second.output, output_contract)
    replay = compare_replay(
        first.output,
        second.output,
        first_process_pid=first.device.provider_pid,
        second_process_pid=second.device.provider_pid,
        tolerance=replay_tolerance,
        save_succeeded=first.save_succeeded,
        reload_succeeded=second.reload_succeeded,
        re_predict_succeeded=second.re_predict_succeeded,
    )
    if first_output.observed_shape != second_output.observed_shape:
        raise CertificationVerificationError("replay output shapes differ")
    checks = RuntimeCheckSummary(
        load_success=first.load_success and second.load_success,
        input_validation_success=(
            first.input_validation_success and second.input_validation_success
        ),
        inference_success=first.inference_success and second.inference_success,
        process_exit_success=True,
        output=second_output,
        device=second.device,
        replay=replay,
    )
    runtime_status = (
        RuntimeStatus.RUNTIME_CERTIFIED
        if evidence_origin == EvidenceOrigin.REAL
        else RuntimeStatus.PARTIALLY_VERIFIED
    )
    return CertificationReport(
        certification_id=certification_id,
        profile=profile,
        evidence_origin=evidence_origin,
        runtime_status=runtime_status,
        accuracy_status=AccuracyStatus.NOT_EVALUATED,
        request=request,
        package=package,
        model=model,
        snapshot=snapshot,
        process_runs=[first.execution, second.execution],
        checks=checks,
        artifacts=[],
    )


def execute_two_process_certification(
    *,
    certification_id: str,
    profile: CertificationProfile,
    evidence_origin: EvidenceOrigin,
    request: RequestIdentity,
    package: PackageIdentity,
    model: ModelIdentity,
    snapshot: SnapshotIdentity,
    output_contract: OutputContract,
    request_payload: object,
    first_command: CommandSpec,
    second_command: CommandSpec,
    executor: Executor,
    observation_loader: ObservationLoader,
    package_artifact_path: Path | None = None,
    package_version_reader: Callable[[str], str] | None = None,
    replay_tolerance: float = 0.0,
) -> CertificationReport:
    """Execute two provider-neutral commands through an injected executor and verify evidence."""

    verify_request_identity(request_payload, request)
    if package_version_reader is None:
        verify_package_identity(package, artifact_path=package_artifact_path)
    else:
        verify_package_identity(
            package,
            artifact_path=package_artifact_path,
            version_reader=package_version_reader,
        )
    verify_snapshot_identity(snapshot)
    first_execution = executor.execute(first_command, run_label="run-a")
    first = observation_loader("run-a", first_execution)
    if first.execution != first_execution:
        raise CertificationVerificationError("observation replaced executor process evidence")
    second_execution = executor.execute(second_command, run_label="run-b")
    second = observation_loader("run-b", second_execution)
    if second.execution != second_execution:
        raise CertificationVerificationError("observation replaced executor process evidence")
    return build_certification_report(
        certification_id=certification_id,
        profile=profile,
        evidence_origin=evidence_origin,
        request=request,
        package=package,
        model=model,
        snapshot=snapshot,
        output_contract=output_contract,
        first=first,
        second=second,
        replay_tolerance=replay_tolerance,
    )

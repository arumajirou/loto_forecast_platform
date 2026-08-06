from __future__ import annotations

import hashlib
import stat
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.runtime_certification.artifacts import (
    ArtifactVerificationError,
    atomic_write_json,
    build_artifact_manifest,
    create_evidence_zip,
    verify_evidence_zip,
    verify_sha256s,
    write_sha256s,
)
from loto.runtime_certification.contracts import (
    ArtifactIdentity,
    CertificationReport,
    CommandSpec,
    DeviceEvidence,
    GPUProcessSample,
    ModelIdentity,
    OutputContract,
    PackageIdentity,
    ProcessExecution,
    RequestIdentity,
    SnapshotIdentity,
)
from loto.runtime_certification.identity import (
    IdentityVerificationError,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    verify_package_identity,
    verify_request_identity,
    verify_snapshot_identity,
)
from loto.runtime_certification.output_validation import OutputValidationError, validate_output
from loto.runtime_certification.replay import ReplayValidationError, compare_replay
from loto.runtime_certification.statuses import (
    AccuracyStatus,
    CertificationProfile,
    EvidenceOrigin,
    RuntimeStatus,
)
from loto.runtime_certification.subprocess_runner import Executor
from loto.runtime_certification.verifier import (
    CertificationVerificationError,
    RunObservation,
    build_certification_report,
    execute_two_process_certification,
)

HEX = "0" * 64
REQUEST_PAYLOAD = {"history": [1.0, 2.0], "horizon": 1}
NOW = datetime(2026, 8, 6, 5, 0, tzinfo=UTC)


def _snapshot(tmp_path: Path) -> SnapshotIdentity:
    root = tmp_path / "revision-1"
    root.mkdir(exist_ok=True)
    artifact = root / "model.bin"
    artifact.write_bytes(b"model-bytes")
    return SnapshotIdentity(
        snapshot_root=str(root),
        expected_revision="revision-1",
        artifacts=[
            ArtifactIdentity(
                relative_path="model.bin",
                sha256=sha256_file(artifact),
                size_bytes=artifact.stat().st_size,
                role="weight",
            )
        ],
    )


def _request(device: str = "cpu", *, valid_hash: bool = False) -> RequestIdentity:
    digest = sha256_bytes(canonical_json_bytes(REQUEST_PAYLOAD)) if valid_hash else HEX
    return RequestIdentity(
        request_id="request-1",
        request_sha256=digest,
        seed=1,
        requested_device=device,
        input_schema_id="fake-provider-request-v1",
    )


def _package(*, artifact_sha256: str | None = None) -> PackageIdentity:
    return PackageIdentity(
        distribution="fake-provider",
        version="1.0.0",
        artifact_sha256=artifact_sha256,
        source_revision="source-revision-1",
    )


def _model() -> ModelIdentity:
    return ModelIdentity(
        model_id="fake-model",
        repository_id="example/fake-model",
        revision="revision-1",
        config_sha256=HEX,
        weight_sha256=HEX,
    )


def _execution(
    label: str,
    pid: int | None = None,
    *,
    exit_code: int | None = 0,
) -> ProcessExecution:
    return ProcessExecution(
        run_label=label,
        process_pid=pid,
        started_at_utc=NOW,
        finished_at_utc=NOW + timedelta(seconds=1),
        exit_code=exit_code,
        timed_out=exit_code is None,
        stdout_sha256=HEX,
        stderr_sha256=HEX,
        response_sha256=HEX,
    )


def _cpu_device(pid: int, origin: EvidenceOrigin) -> DeviceEvidence:
    return DeviceEvidence(
        requested_device="cpu",
        effective_device="cpu",
        cpu_fallback=False,
        provider_pid=pid,
        provider_gpu_pid=None,
        gpu_uuid=None,
        peak_vram_bytes=0,
        external_gpu_samples=[],
        pid_released_after_exit=True,
        origin=origin,
    )


def _gpu_device(pid: int, origin: EvidenceOrigin) -> DeviceEvidence:
    return DeviceEvidence(
        requested_device="cuda",
        effective_device="cuda",
        cpu_fallback=False,
        provider_pid=pid,
        provider_gpu_pid=pid,
        gpu_uuid="GPU-FAKE-UUID",
        peak_vram_bytes=1024,
        external_gpu_samples=[
            GPUProcessSample(
                provider_pid=pid,
                gpu_uuid="GPU-FAKE-UUID",
                used_memory_bytes=1024,
                observed_at_utc=NOW,
            )
        ],
        pid_released_after_exit=True,
        origin=origin,
    )


def _observation(
    label: str,
    pid: int,
    origin: EvidenceOrigin,
    *,
    device: str = "cpu",
    output: object | None = None,
) -> RunObservation:
    evidence = _cpu_device(pid, origin) if device == "cpu" else _gpu_device(pid, origin)
    return RunObservation(
        execution=_execution(label, pid),
        output=output if output is not None else [[1.0, 2.0], [3.0, 4.0]],
        device=evidence,
    )


def test_strict_contract_rejects_unknown_fields_and_type_coercion() -> None:
    with pytest.raises(ValidationError):
        RequestIdentity.model_validate(
            {
                "request_id": "x",
                "request_sha256": HEX,
                "seed": "1",
                "requested_device": "cpu",
                "input_schema_id": "v1",
                "unknown": True,
            }
        )


def test_request_and_package_identity_are_verifiable_with_injected_metadata(
    tmp_path: Path,
) -> None:
    request = _request(valid_hash=True)
    assert verify_request_identity(REQUEST_PAYLOAD, request) == request.request_sha256
    with pytest.raises(IdentityVerificationError, match="request SHA-256"):
        verify_request_identity({"history": [9.0]}, request)

    wheel = tmp_path / "fake-provider.whl"
    wheel.write_bytes(b"wheel-bytes")
    package = _package(artifact_sha256=sha256_file(wheel))
    assert verify_package_identity(
        package,
        artifact_path=wheel,
        version_reader=lambda name: "1.0.0",
    ) == "1.0.0"
    with pytest.raises(IdentityVerificationError, match="version mismatch"):
        verify_package_identity(package, version_reader=lambda name: "2.0.0")


def test_real_cpu_smoke_certifies_runtime_but_not_accuracy(tmp_path: Path) -> None:
    report = build_certification_report(
        certification_id="cpu-real",
        profile=CertificationProfile.CPU_SMOKE,
        evidence_origin=EvidenceOrigin.REAL,
        request=_request("cpu"),
        package=_package(),
        model=_model(),
        snapshot=_snapshot(tmp_path),
        output_contract=OutputContract(expected_shape=[2, 2]),
        first=_observation("run-a", 101, EvidenceOrigin.REAL),
        second=_observation("run-b", 202, EvidenceOrigin.REAL),
    )

    assert report.runtime_status == RuntimeStatus.RUNTIME_CERTIFIED
    assert report.profile == CertificationProfile.CPU_SMOKE
    assert report.accuracy_status == AccuracyStatus.NOT_EVALUATED


def test_synthetic_gpu_evidence_remains_partially_verified(tmp_path: Path) -> None:
    report = build_certification_report(
        certification_id="gpu-synthetic",
        profile=CertificationProfile.GPU_FORMAL,
        evidence_origin=EvidenceOrigin.SYNTHETIC,
        request=_request("cuda"),
        package=_package(),
        model=_model(),
        snapshot=_snapshot(tmp_path),
        output_contract=OutputContract(expected_shape=[2, 2]),
        first=_observation("run-a", 301, EvidenceOrigin.SYNTHETIC, device="cuda"),
        second=_observation("run-b", 302, EvidenceOrigin.SYNTHETIC, device="cuda"),
    )

    assert report.runtime_status == RuntimeStatus.PARTIALLY_VERIFIED
    assert report.profile == CertificationProfile.GPU_FORMAL
    assert report.accuracy_status == AccuracyStatus.NOT_EVALUATED


def test_synthetic_evidence_cannot_be_relabelled_as_runtime_certified(tmp_path: Path) -> None:
    partial = build_certification_report(
        certification_id="gpu-synthetic",
        profile=CertificationProfile.GPU_FORMAL,
        evidence_origin=EvidenceOrigin.SYNTHETIC,
        request=_request("cuda"),
        package=_package(),
        model=_model(),
        snapshot=_snapshot(tmp_path),
        output_contract=OutputContract(expected_shape=[2, 2]),
        first=_observation("run-a", 401, EvidenceOrigin.SYNTHETIC, device="cuda"),
        second=_observation("run-b", 402, EvidenceOrigin.SYNTHETIC, device="cuda"),
    )
    payload = partial.model_dump(mode="python")
    payload["runtime_status"] = RuntimeStatus.RUNTIME_CERTIFIED

    with pytest.raises(ValidationError, match="synthetic or injected evidence"):
        CertificationReport.model_validate(payload)


def test_report_rejects_device_origin_mismatch(tmp_path: Path) -> None:
    with pytest.raises(CertificationVerificationError, match="origin"):
        build_certification_report(
            certification_id="origin-mismatch",
            profile=CertificationProfile.CPU_SMOKE,
            evidence_origin=EvidenceOrigin.REAL,
            request=_request("cpu"),
            package=_package(),
            model=_model(),
            snapshot=_snapshot(tmp_path),
            output_contract=OutputContract(expected_shape=[2, 2]),
            first=_observation("run-a", 501, EvidenceOrigin.INJECTED_FAKE),
            second=_observation("run-b", 502, EvidenceOrigin.INJECTED_FAKE),
        )


def test_output_shape_finite_and_quantile_monotonicity() -> None:
    contract = OutputContract(
        expected_shape=[2, 3, 2],
        quantile_axis=1,
        quantile_levels=[0.1, 0.5, 0.9],
    )
    valid = [
        [[1.0, 2.0], [2.0, 3.0], [3.0, 4.0]],
        [[5.0, 6.0], [6.0, 7.0], [7.0, 8.0]],
    ]
    evidence = validate_output(valid, contract)
    assert evidence.observed_shape == [2, 3, 2]
    assert evidence.quantile_monotonic is True

    invalid = [
        [[1.0, 2.0], [0.5, 3.0], [3.0, 4.0]],
        [[5.0, 6.0], [6.0, 7.0], [7.0, 8.0]],
    ]
    with pytest.raises(OutputValidationError, match="not monotonic"):
        validate_output(invalid, contract)


def test_replay_requires_distinct_processes_and_bounded_difference() -> None:
    with pytest.raises(ReplayValidationError, match="distinct"):
        compare_replay(
            [1.0],
            [1.0],
            first_process_pid=1,
            second_process_pid=1,
        )

    evidence = compare_replay(
        [1.0, 2.0],
        [1.0, 2.0001],
        first_process_pid=1,
        second_process_pid=2,
        tolerance=0.001,
    )
    assert evidence.exact_match is False
    assert evidence.maximum_absolute_difference <= evidence.tolerance

    with pytest.raises(ReplayValidationError):
        compare_replay(
            [1.0],
            [2.0],
            first_process_pid=1,
            second_process_pid=2,
            tolerance=0.0,
        )


def test_snapshot_identity_rejects_hash_drift_and_symlink(tmp_path: Path) -> None:
    identity = _snapshot(tmp_path)
    assert verify_snapshot_identity(identity)["model.bin"].endswith("model.bin")

    model_path = Path(identity.snapshot_root) / "model.bin"
    model_path.write_bytes(b"changed")
    with pytest.raises(IdentityVerificationError, match="size mismatch|SHA-256 mismatch"):
        verify_snapshot_identity(identity)

    model_path.write_bytes(b"model-bytes")
    target = Path(identity.snapshot_root) / "target.bin"
    target.write_bytes(b"model-bytes")
    model_path.unlink()
    try:
        model_path.symlink_to(target.name)
    except OSError:
        pytest.skip("symlinks are unavailable")
    with pytest.raises(IdentityVerificationError, match="symlink"):
        verify_snapshot_identity(identity)


class FakeExecutor(Executor):
    def __init__(self) -> None:
        self.labels: list[str] = []

    def execute(self, spec: CommandSpec, *, run_label: str) -> ProcessExecution:
        self.labels.append(run_label)
        assert spec.argv == ["fake-provider", "predict"]
        return _execution(run_label)


def test_injected_fake_executor_can_test_contract_without_cuda(tmp_path: Path) -> None:
    executor = FakeExecutor()
    commands = CommandSpec(
        argv=["fake-provider", "predict"],
        cwd=str(tmp_path),
        timeout_seconds=10.0,
    )

    def load_observation(label: str, execution: ProcessExecution) -> RunObservation:
        pid = 601 if label == "run-a" else 602
        return RunObservation(
            execution=execution,
            output=[[1.0, 2.0], [3.0, 4.0]],
            device=_cpu_device(pid, EvidenceOrigin.INJECTED_FAKE),
        )

    report = execute_two_process_certification(
        certification_id="fake-executor",
        profile=CertificationProfile.CPU_SMOKE,
        evidence_origin=EvidenceOrigin.INJECTED_FAKE,
        request=_request("cpu", valid_hash=True),
        package=_package(),
        model=_model(),
        snapshot=_snapshot(tmp_path),
        output_contract=OutputContract(expected_shape=[2, 2]),
        request_payload=REQUEST_PAYLOAD,
        first_command=commands,
        second_command=commands,
        executor=executor,
        observation_loader=load_observation,
        package_version_reader=lambda name: "1.0.0",
    )

    assert executor.labels == ["run-a", "run-b"]
    assert report.runtime_status == RuntimeStatus.PARTIALLY_VERIFIED


def test_timeout_and_nonzero_exit_fail_closed(tmp_path: Path) -> None:
    timeout = RunObservation(
        execution=_execution("run-a", exit_code=None),
        output=[[1.0]],
        device=_cpu_device(701, EvidenceOrigin.INJECTED_FAKE),
    )
    good = _observation(
        "run-b",
        702,
        EvidenceOrigin.INJECTED_FAKE,
        output=[[1.0]],
    )
    with pytest.raises(CertificationVerificationError, match="timed out"):
        build_certification_report(
            certification_id="timeout",
            profile=CertificationProfile.CPU_SMOKE,
            evidence_origin=EvidenceOrigin.INJECTED_FAKE,
            request=_request("cpu"),
            package=_package(),
            model=_model(),
            snapshot=_snapshot(tmp_path),
            output_contract=OutputContract(expected_shape=[1, 1]),
            first=timeout,
            second=good,
        )

    failed = RunObservation(
        execution=_execution("run-a", exit_code=4),
        output=[[1.0]],
        device=_cpu_device(703, EvidenceOrigin.INJECTED_FAKE),
    )
    with pytest.raises(CertificationVerificationError, match="exit"):
        build_certification_report(
            certification_id="exit",
            profile=CertificationProfile.CPU_SMOKE,
            evidence_origin=EvidenceOrigin.INJECTED_FAKE,
            request=_request("cpu"),
            package=_package(),
            model=_model(),
            snapshot=_snapshot(tmp_path),
            output_contract=OutputContract(expected_shape=[1, 1]),
            first=failed,
            second=good,
        )


def test_manifest_sha256s_and_tamper_detection(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    atomic_write_json(root / "report.json", {"status": "PARTIALLY_VERIFIED"})
    (root / "stdout.txt").write_text("ok\n", encoding="utf-8")

    records = build_artifact_manifest(root)
    assert [record.relative_path for record in records] == ["report.json", "stdout.txt"]
    manifest = root / "SHA256SUMS"
    write_sha256s(root, manifest)
    assert len(verify_sha256s(root, manifest)) == 2

    (root / "stdout.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ArtifactVerificationError, match="hash mismatch"):
        verify_sha256s(root, manifest)


def test_evidence_zip_is_deterministic_and_sidecar_verified(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    (root / "b.txt").write_text("b\n", encoding="utf-8")
    first, first_sidecar, first_digest = create_evidence_zip(root, tmp_path / "first.zip")
    second, second_sidecar, second_digest = create_evidence_zip(root, tmp_path / "second.zip")

    assert first.read_bytes() == second.read_bytes()
    assert first_digest == second_digest
    assert verify_evidence_zip(first, first_sidecar) == first_digest
    assert verify_evidence_zip(second, second_sidecar) == second_digest


def test_evidence_zip_rejects_traversal_and_symlink_members(tmp_path: Path) -> None:
    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("../escape.txt", "bad")
    traversal_digest = hashlib.sha256(traversal.read_bytes()).hexdigest()
    traversal_sidecar = tmp_path / "traversal.zip.sha256"
    traversal_sidecar.write_text(
        f"{traversal_digest}  traversal.zip\n",
        encoding="utf-8",
    )
    with pytest.raises(ArtifactVerificationError, match="unsafe ZIP member"):
        verify_evidence_zip(traversal, traversal_sidecar)

    symlink_zip = tmp_path / "symlink.zip"
    with zipfile.ZipFile(symlink_zip, "w") as archive:
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "target")
    symlink_digest = hashlib.sha256(symlink_zip.read_bytes()).hexdigest()
    symlink_sidecar = tmp_path / "symlink.zip.sha256"
    symlink_sidecar.write_text(f"{symlink_digest}  symlink.zip\n", encoding="utf-8")
    with pytest.raises(ArtifactVerificationError, match="unsupported ZIP member"):
        verify_evidence_zip(symlink_zip, symlink_sidecar)

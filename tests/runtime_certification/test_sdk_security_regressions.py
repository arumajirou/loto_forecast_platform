from __future__ import annotations

import hashlib
import os
import sys
import time
import zipfile
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.runtime_certification.artifacts import (
    ArtifactVerificationError,
    atomic_write_json,
    create_evidence_zip,
    verify_evidence_zip,
)
from loto.runtime_certification.contracts import (
    ArtifactIdentity,
    CommandSpec,
    DeviceEvidence,
    ModelIdentity,
    OutputContract,
    PackageIdentity,
    ProcessExecution,
    RequestIdentity,
    SnapshotIdentity,
)
from loto.runtime_certification.identity import canonical_json_bytes, sha256_bytes, sha256_file
from loto.runtime_certification.statuses import (
    CertificationProfile,
    EvidenceOrigin,
)
from loto.runtime_certification.subprocess_runner import ExecutionError, SubprocessExecutor
from loto.runtime_certification.verifier import (
    CertificationVerificationError,
    RunObservation,
    _validate_process_binding,
    execute_two_process_certification,
)

HEX = "0" * 64
NOW = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)
REQUEST_PAYLOAD = {"history": [1.0, 2.0], "horizon": 1}


def _execution(label: str, pid: int | None) -> ProcessExecution:
    return ProcessExecution(
        run_label=label,
        process_pid=pid,
        process_identity_sha256=HEX if pid is not None else None,
        started_at_utc=NOW,
        finished_at_utc=NOW + timedelta(seconds=1),
        exit_code=0,
        timed_out=False,
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
        provider_process_identity_sha256=HEX if origin == EvidenceOrigin.REAL else None,
        provider_gpu_pid=None,
        gpu_uuid=None,
        peak_vram_bytes=0,
        external_gpu_samples=[],
        pid_released_after_exit=True,
        origin=origin,
    )


def _write_zip_sidecar(zip_path: Path) -> Path:
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sidecar = zip_path.with_name(f"{zip_path.name}.sha256")
    sidecar.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    return sidecar


@pytest.mark.parametrize("unsafe_path", ["line\nbreak.txt", "nul\x00byte.txt", "del\x7fname.txt"])
def test_artifact_identity_rejects_control_characters(unsafe_path: str) -> None:
    with pytest.raises(ValidationError, match="control characters"):
        ArtifactIdentity(
            relative_path=unsafe_path,
            sha256=HEX,
            size_bytes=0,
            role="runtime_evidence",
        )


def test_evidence_zip_rejects_control_character_member(tmp_path: Path) -> None:
    archive_path = tmp_path / "control.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("line\nbreak.txt", "unsafe")

    with pytest.raises(ArtifactVerificationError, match="unsafe ZIP member"):
        verify_evidence_zip(archive_path, _write_zip_sidecar(archive_path))


def test_contracts_reject_non_finite_values_and_non_utc_timestamps() -> None:
    with pytest.raises(ValidationError):
        OutputContract(expected_shape=[1], monotonic_tolerance=float("inf"))
    jst = timezone(timedelta(hours=9))
    with pytest.raises(ValidationError, match="must be UTC"):
        ProcessExecution(
            run_label="non-utc",
            process_pid=1,
            started_at_utc=datetime(2026, 8, 7, tzinfo=jst),
            finished_at_utc=datetime(2026, 8, 7, 0, 0, 1, tzinfo=jst),
            exit_code=0,
            stdout_sha256=HEX,
            stderr_sha256=HEX,
        )


def test_atomic_artifact_write_refuses_implicit_overwrite_and_symlink(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    atomic_write_json(output, {"status": "first"})
    with pytest.raises(ArtifactVerificationError, match="overwrite"):
        atomic_write_json(output, {"status": "second"})

    victim = tmp_path / "victim.txt"
    victim.write_text("unchanged", encoding="utf-8")
    linked = tmp_path / "linked.json"
    try:
        linked.symlink_to(victim)
    except OSError:
        pytest.skip("symlinks are unavailable")
    with pytest.raises(ArtifactVerificationError, match="symlink"):
        atomic_write_json(linked, {"status": "unsafe"})
    assert victim.read_text(encoding="utf-8") == "unchanged"


def test_evidence_zip_refuses_implicit_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "result.json").write_text("{}\n", encoding="utf-8")
    output = tmp_path / "evidence.zip"
    create_evidence_zip(root, output)
    with pytest.raises(ArtifactVerificationError, match="overwrite"):
        create_evidence_zip(root, output)


def test_subprocess_executor_records_real_process_pid(tmp_path: Path) -> None:
    execution = SubprocessExecutor().execute(
        CommandSpec(
            argv=[
                sys.executable,
                "-c",
                "import time; print('runtime-certification'); time.sleep(0.2)",
            ],
            cwd=str(tmp_path),
            timeout_seconds=10.0,
        ),
        run_label="pid-probe",
    )

    assert execution.process_pid is not None
    assert execution.process_pid > 0
    if sys.platform.startswith("linux") and Path(f"/proc/{os.getpid()}/stat").exists():
        assert execution.process_identity_sha256 is not None
    assert execution.exit_code == 0
    assert execution.timed_out is False
    assert execution.stdout_sha256 == hashlib.sha256(b"runtime-certification\n").hexdigest()


@pytest.mark.parametrize(
    "name",
    ["GITHUB_TOKEN", "OPENAI_API_KEY", "LD_PRELOAD", "PYTHONPATH"],
)
def test_command_spec_rejects_sensitive_and_process_injection_environment(name: str) -> None:
    with pytest.raises(ValidationError):
        CommandSpec(
            argv=[sys.executable, "-c", "print('safe')"],
            cwd="/tmp",
            timeout_seconds=10.0,
            environment={name: "do-not-pass"},
        )


def test_subprocess_executor_does_not_inherit_secret_environment(tmp_path: Path) -> None:
    base_environment = dict(os.environ)
    base_environment["RUNTIME_SECRET_TOKEN"] = "top-secret-value"
    execution = SubprocessExecutor(base_environment=base_environment).execute(
        CommandSpec(
            argv=[
                sys.executable,
                "-c",
                "import os; print('RUNTIME_SECRET_TOKEN' in os.environ)",
            ],
            cwd=str(tmp_path),
            timeout_seconds=10.0,
        ),
        run_label="environment-probe",
    )
    assert execution.stdout_sha256 == hashlib.sha256(b"False\n").hexdigest()


def test_subprocess_executor_rejects_symlink_cwd(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable")
    with pytest.raises(ExecutionError, match="symlink"):
        SubprocessExecutor().execute(
            CommandSpec(
                argv=[sys.executable, "-c", "print('unsafe-cwd')"],
                cwd=str(linked),
                timeout_seconds=10.0,
            ),
            run_label="cwd-probe",
        )


def test_subprocess_start_error_redacts_os_error_details(tmp_path: Path) -> None:
    secret_path = str(tmp_path / "secret-value-must-not-appear")
    with pytest.raises(ExecutionError) as raised:
        SubprocessExecutor().execute(
            CommandSpec(
                argv=[secret_path],
                cwd=str(tmp_path),
                timeout_seconds=10.0,
            ),
            run_label="start-failure",
        )
    assert "secret-value-must-not-appear" not in str(raised.value)


def test_subprocess_output_limit_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ExecutionError, match="output exceeded"):
        SubprocessExecutor(max_stream_bytes=128).execute(
            CommandSpec(
                argv=[sys.executable, "-c", "print('x' * 4096)"],
                cwd=str(tmp_path),
                timeout_seconds=10.0,
            ),
            run_label="output-limit",
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group regression")
def test_timeout_kills_process_group_and_reaps_direct_child(tmp_path: Path) -> None:
    child_pid_path = tmp_path / "child.pid"
    script = (
        "import pathlib,subprocess,sys,time;"
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']);"
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(p.pid));"
        "time.sleep(60)"
    )
    execution = SubprocessExecutor().execute(
        CommandSpec(
            argv=[sys.executable, "-c", script],
            cwd=str(tmp_path),
            timeout_seconds=0.25,
        ),
        run_label="timeout-tree",
    )
    assert execution.timed_out is True
    assert execution.process_pid is not None
    with pytest.raises(ChildProcessError):
        os.waitpid(execution.process_pid, os.WNOHANG)
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    for _ in range(100):
        proc_stat = Path(f"/proc/{child_pid}/stat")
        if not proc_stat.exists() or proc_stat.read_text(encoding="ascii").split()[2] == "Z":
            break
        time.sleep(0.01)
    else:
        pytest.fail("spawned child process remained active after timeout")


def test_process_binding_requires_real_pid_and_exact_device_pid() -> None:
    missing_pid = RunObservation(
        execution=_execution("run-a", None),
        output=[[1.0]],
        device=_cpu_device(101, EvidenceOrigin.REAL),
    )
    with pytest.raises(CertificationVerificationError, match="requires an observed process PID"):
        _validate_process_binding(missing_pid, evidence_origin=EvidenceOrigin.REAL)

    mismatched_pid = RunObservation(
        execution=_execution("run-a", 102),
        output=[[1.0]],
        device=_cpu_device(101, EvidenceOrigin.SYNTHETIC),
    )
    with pytest.raises(CertificationVerificationError, match="differs from device provider PID"):
        _validate_process_binding(mismatched_pid, evidence_origin=EvidenceOrigin.SYNTHETIC)

    identity_mismatch = RunObservation(
        execution=_execution("run-a", 103),
        output=[[1.0]],
        device=DeviceEvidence(
            requested_device="cpu",
            effective_device="cpu",
            cpu_fallback=False,
            provider_pid=103,
            provider_process_identity_sha256="1" * 64,
            provider_gpu_pid=None,
            gpu_uuid=None,
            peak_vram_bytes=0,
            external_gpu_samples=[],
            pid_released_after_exit=True,
            origin=EvidenceOrigin.REAL,
        ),
    )
    with pytest.raises(CertificationVerificationError, match="process identity differs"):
        _validate_process_binding(identity_mismatch, evidence_origin=EvidenceOrigin.REAL)


class _Executor:
    def execute(self, spec: CommandSpec, *, run_label: str) -> ProcessExecution:
        del spec
        return _execution(run_label, 201 if run_label == "run-a" else 202)


def test_observation_loader_cannot_replace_executor_evidence(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "revision-1"
    snapshot_root.mkdir()
    artifact_path = snapshot_root / "model.bin"
    artifact_path.write_bytes(b"model")
    snapshot = SnapshotIdentity(
        snapshot_root=str(snapshot_root),
        expected_revision="revision-1",
        artifacts=[
            ArtifactIdentity(
                relative_path="model.bin",
                sha256=sha256_file(artifact_path),
                size_bytes=artifact_path.stat().st_size,
                role="weight",
            )
        ],
    )
    request = RequestIdentity(
        request_id="request-1",
        request_sha256=sha256_bytes(canonical_json_bytes(REQUEST_PAYLOAD)),
        seed=1,
        requested_device="cpu",
        input_schema_id="fake-request-v1",
    )
    command = CommandSpec(
        argv=["fake-provider", "predict"],
        cwd=str(tmp_path),
        timeout_seconds=10.0,
    )

    def replace_execution(label: str, execution: ProcessExecution) -> RunObservation:
        replacement = execution.model_copy(update={"process_pid": 999})
        return RunObservation(
            execution=replacement,
            output=[[1.0]],
            device=_cpu_device(999, EvidenceOrigin.INJECTED_FAKE),
        )

    with pytest.raises(CertificationVerificationError, match="replaced executor process evidence"):
        execute_two_process_certification(
            certification_id="replacement-rejected",
            profile=CertificationProfile.CPU_SMOKE,
            evidence_origin=EvidenceOrigin.INJECTED_FAKE,
            request=request,
            package=PackageIdentity(distribution="fake-provider", version="1.0.0"),
            model=ModelIdentity(
                model_id="fake-model",
                repository_id="example/fake-model",
                revision="revision-1",
            ),
            snapshot=snapshot,
            output_contract=OutputContract(expected_shape=[1, 1]),
            request_payload=REQUEST_PAYLOAD,
            first_command=command,
            second_command=command,
            executor=_Executor(),
            observation_loader=replace_execution,
            package_version_reader=lambda distribution: "1.0.0",
        )

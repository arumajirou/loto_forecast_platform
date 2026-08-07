from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from loto.neuralforecast.auto_segrnn.runtime_certification import (
    AutoSegRNNCertificationError,
    RuntimeSDK,
    build_command_specs,
    build_common_identities,
    build_observation_loader,
    certify_auto_segrnn,
)
from loto.neuralforecast.auto_segrnn.runtime_contracts import (
    AutoSegRNNRuntimeRequest,
    AutoSegRNNWorkerResponse,
    SourceFileRecord,
)
from loto.neuralforecast.auto_segrnn.runtime_source import PreparedSource


class Record:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class EnumValue:
    def __init__(self, value: str):
        self.value = value


class EnumGroup:
    REAL = EnumValue("REAL")
    CPU_SMOKE = EnumValue("CPU_SMOKE")
    GPU_FORMAL = EnumValue("GPU_FORMAL")


def _sdk() -> RuntimeSDK:
    root = SimpleNamespace(
        RequestIdentity=Record,
        PackageIdentity=Record,
        ModelIdentity=Record,
        SnapshotIdentity=Record,
        OutputContract=Record,
        CommandSpec=Record,
        DeviceEvidence=Record,
        RunObservation=Record,
    )
    contracts = SimpleNamespace(
        ArtifactIdentity=Record,
        GPUProcessSample=Record,
    )
    statuses = SimpleNamespace(
        EvidenceOrigin=EnumGroup,
        CertificationProfile=EnumGroup,
    )
    return RuntimeSDK(
        root=root,
        contracts=contracts,
        statuses=statuses,
        verifier=SimpleNamespace(),
        runner=SimpleNamespace(),
        artifacts=SimpleNamespace(),
    )


def _request(tmp_path: Path, **overrides: object) -> AutoSegRNNRuntimeRequest:
    payload = {
        "run_id": "adapter-test",
        "profile": "CPU_SMOKE",
        "execution_mode": "direct",
        "requested_device": "cpu",
        "source_revision": "a" * 40,
        "source_tree_sha256": "b" * 64,
        "history_length": 96,
        "working_directory": str((tmp_path / "repo").resolve()),
    }
    payload.update(overrides)
    return AutoSegRNNRuntimeRequest.model_validate(payload)


def _prepared_source(tmp_path: Path) -> PreparedSource:
    snapshot = tmp_path / "snapshot" / ("a" * 40)
    snapshot.mkdir(parents=True)
    file_path = snapshot / "src/model.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("model\n", encoding="utf-8")
    return PreparedSource(
        snapshot_root=snapshot,
        source_revision="a" * 40,
        source_tree_sha256="b" * 64,
        files=(
            SourceFileRecord(
                relative_path="src/model.py",
                sha256="c" * 64,
                size_bytes=6,
            ),
        ),
    )


def test_common_identities_bind_local_source_snapshot(tmp_path: Path) -> None:
    identities = build_common_identities(
        _request(tmp_path),
        prepared_source=_prepared_source(tmp_path),
        sdk=_sdk(),
    )
    assert identities["model"].model_id == "nf-local-auto-segrnn"
    assert identities["model"].repository_id == "arumajirou/loto_forecast_platform"
    assert identities["model"].config_sha256 == "b" * 64
    assert identities["snapshot"].expected_revision == "a" * 40
    assert identities["snapshot"].artifacts[0].role == "source_code"


def test_command_specs_are_explicit_and_cpu_isolated(tmp_path: Path) -> None:
    request = _request(tmp_path, execution_mode="ray")
    request_path = tmp_path / "request.json"
    request_path.write_text("{}", encoding="utf-8")
    first, second = build_command_specs(
        request,
        request_path=request_path,
        output_root=tmp_path / "out",
        sdk=_sdk(),
        python_executable="/usr/bin/python3",
    )
    assert first.argv[:3] == [
        "/usr/bin/python3",
        "-m",
        "loto.neuralforecast.auto_segrnn.runtime_worker",
    ]
    assert "run-a" in first.argv
    assert "run-b" in second.argv
    assert first.environment["CUDA_VISIBLE_DEVICES"] == ""
    assert first.environment["RAY_TMPDIR"].endswith("run-a/ray_tmp")


def test_observation_loader_maps_cpu_response(tmp_path: Path) -> None:
    request = _request(tmp_path, execution_mode="optuna")
    output_root = tmp_path / "out"
    response_path = output_root / "processes" / "run-a" / "WORKER_RESPONSE.json"
    response_path.parent.mkdir(parents=True)
    response = AutoSegRNNWorkerResponse(
        status="PASS",
        run_label="run-a",
        execution_mode="optuna",
        provider_pid=321,
        package_version="3.2.0",
        source_revision="a" * 40,
        source_tree_sha256="b" * 64,
        requested_device="cpu",
        effective_device="cpu",
        cpu_fallback=False,
        peak_vram_bytes=0,
        output=((4.0,),),
        pre_reload_output=((4.0,),),
        source_verified=True,
        package_verified=True,
        load_success=True,
        input_validation_success=True,
        fit_success=True,
        inference_success=True,
        save_succeeded=True,
        reload_succeeded=True,
        re_predict_succeeded=True,
        auto_backend_executed=True,
        maximum_reload_difference=0.0,
        bundle_path="/tmp/bundle",
        fitted_model_class="SegRNN",
    )
    response_path.write_text(
        json.dumps(response.model_dump(mode="json")),
        encoding="utf-8",
    )
    execution = Record(exit_code=0, timed_out=False)
    observation = build_observation_loader(
        output_root,
        request=request,
        sdk=_sdk(),
    )("run-a", execution)
    assert observation.output == [[4.0]]
    assert observation.device.provider_pid == 321
    assert observation.device.pid_released_after_exit is True


def test_observation_loader_rejects_source_drift(tmp_path: Path) -> None:
    request = _request(tmp_path)
    output_root = tmp_path / "out"
    response_path = output_root / "processes" / "run-a" / "WORKER_RESPONSE.json"
    response_path.parent.mkdir(parents=True)
    response = AutoSegRNNWorkerResponse(
        status="FAILED",
        run_label="run-a",
        execution_mode="direct",
        provider_pid=321,
        requested_device="cpu",
        error_type="SourceIdentityError",
        error_message="source drift",
    )
    response_path.write_text(
        json.dumps(response.model_dump(mode="json")),
        encoding="utf-8",
    )
    with pytest.raises(AutoSegRNNCertificationError, match="source drift"):
        build_observation_loader(
            output_root,
            request=request,
            sdk=_sdk(),
        )("run-a", Record(exit_code=2, timed_out=False))


def test_certifier_seals_structured_failure(tmp_path: Path) -> None:
    sdk = _sdk()

    def execute_two_process_certification(**_kwargs):
        raise RuntimeError("provider unavailable")

    def atomic_write_json(path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def write_sha256s(_root: Path, output: Path) -> None:
        output.write_text("sealed\n", encoding="utf-8")

    def verify_sha256s(_root: Path, manifest_path: Path) -> None:
        assert manifest_path.read_text(encoding="utf-8") == "sealed\n"

    def create_evidence_zip(_root: Path, output: Path) -> None:
        output.write_bytes(b"zip")
        output.with_name(f"{output.name}.sha256").write_text("stub", encoding="utf-8")

    sdk.root.execute_two_process_certification = execute_two_process_certification
    sdk = RuntimeSDK(
        root=sdk.root,
        contracts=sdk.contracts,
        statuses=sdk.statuses,
        verifier=sdk.verifier,
        runner=sdk.runner,
        artifacts=SimpleNamespace(
            atomic_write_json=atomic_write_json,
            write_sha256s=write_sha256s,
            verify_sha256s=verify_sha256s,
            create_evidence_zip=create_evidence_zip,
        ),
    )
    repository = tmp_path / "repo"
    repository.mkdir()
    request = _request(tmp_path)
    output_root = tmp_path / "evidence"

    def source_preparer(*_args, **_kwargs):
        prepared = _prepared_source(tmp_path)
        target = output_root / "source_snapshot" / ("a" * 40)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.mkdir()
        return PreparedSource(
            snapshot_root=target,
            source_revision=prepared.source_revision,
            source_tree_sha256=prepared.source_tree_sha256,
            files=prepared.files,
        )

    with pytest.raises(AutoSegRNNCertificationError, match="blocked"):
        certify_auto_segrnn(
            request,
            output_root,
            sdk=sdk,
            executor=object(),
            package_version_reader=lambda _name: "3.2.0",
            source_preparer=source_preparer,
        )
    failure = json.loads((output_root / "CERTIFICATION_FAILURE.json").read_text())
    assert failure["status"] == "BLOCKED"
    assert failure["runtime_certified"] is False
    assert failure["execution_mode"] == "direct"
    assert (output_root / "SHA256SUMS").is_file()
    assert output_root.with_name("evidence.zip").is_file()

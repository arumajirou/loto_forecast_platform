from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from loto.neuralforecast.auto_timellm.contracts import (
    ArchitectureProfile,
    PinnedLLMIdentity,
    SnapshotFileEvidence,
)
from loto.neuralforecast.auto_timellm.runtime_certification import (
    RuntimeSDK,
    build_command_specs,
    build_common_identities,
    build_observation_loader,
)
from loto.neuralforecast.auto_timellm.runtime_contracts import (
    AutoTimeLLMRuntimeRequest,
    AutoTimeLLMWorkerResponse,
)


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


def _evidence(path: Path, relative: str, content: bytes) -> SnapshotFileEvidence:
    target = path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return SnapshotFileEvidence(
        relative_path=relative,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )


def _request(tmp_path: Path) -> AutoTimeLLMRuntimeRequest:
    revision = "b" * 40
    snapshot = tmp_path / revision
    identity = PinnedLLMIdentity(
        repo_id="openai-community/gpt2",
        revision=revision,
        snapshot_path=str(snapshot.resolve()),
        license_id="MIT",
        files=(
            _evidence(snapshot, "config.json", b'{"model_type":"gpt2","n_embd":8,"n_layer":2}'),
            _evidence(snapshot, "tokenizer.json", b"{}"),
            _evidence(snapshot, "model.safetensors", b"weights"),
        ),
    )
    return AutoTimeLLMRuntimeRequest(
        run_id="adapter-test",
        llm_identity=identity,
        profile="CPU_SMOKE",
        requested_device="cpu",
        architecture_profile=ArchitectureProfile.COMPACT,
        history_length=96,
        working_directory=str(tmp_path.resolve()),
    )


def test_common_identities_preserve_model_and_snapshot(tmp_path: Path) -> None:
    identities = build_common_identities(_request(tmp_path), sdk=_sdk())
    assert identities["model"].model_id == "nf-local-auto-timellm"
    assert identities["model"].repository_id == "openai-community/gpt2"
    assert identities["snapshot"].expected_revision == "b" * 40
    roles = {item.relative_path: item.role for item in identities["snapshot"].artifacts}
    assert roles["config.json"] == "model_config"
    assert roles["model.safetensors"] == "model_weight"


def test_command_specs_use_argv_without_shell(tmp_path: Path) -> None:
    request = _request(tmp_path)
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
        "loto.neuralforecast.auto_timellm.runtime_worker",
    ]
    assert "run-a" in first.argv
    assert "run-b" in second.argv
    assert first.environment["HF_HUB_OFFLINE"] == "1"


def test_observation_loader_maps_cpu_response(tmp_path: Path) -> None:
    output_root = tmp_path / "out"
    response_path = output_root / "processes" / "run-a" / "WORKER_RESPONSE.json"
    response_path.parent.mkdir(parents=True)
    response = AutoTimeLLMWorkerResponse(
        status="PASS",
        run_label="run-a",
        provider_pid=321,
        package_version="3.2.0",
        requested_device="cpu",
        effective_device="cpu",
        cpu_fallback=False,
        peak_vram_bytes=0,
        output=((4.0,),),
        pre_reload_output=((4.0,),),
        load_success=True,
        input_validation_success=True,
        inference_success=True,
        save_succeeded=True,
        reload_succeeded=True,
        re_predict_succeeded=True,
        maximum_reload_difference=0.0,
        bundle_path="/tmp/bundle",
    )
    response_path.write_text(
        json.dumps(response.model_dump(mode="json")),
        encoding="utf-8",
    )
    execution = Record(exit_code=0, timed_out=False)
    observation = build_observation_loader(output_root, sdk=_sdk())("run-a", execution)
    assert observation.output == [[4.0]]
    assert observation.device.provider_pid == 321
    assert observation.device.pid_released_after_exit is True
    assert observation.device.origin.value == "REAL"


def test_certifier_seals_structured_failure(tmp_path: Path) -> None:
    import pytest

    from loto.neuralforecast.auto_timellm.runtime_certification import (
        AutoTimeLLMCertificationError,
        certify_auto_timellm,
    )

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
    output_root = tmp_path / "evidence"
    with pytest.raises(AutoTimeLLMCertificationError, match="blocked"):
        certify_auto_timellm(
            _request(tmp_path),
            output_root,
            sdk=sdk,
            executor=object(),
            package_version_reader=lambda _name: "3.2.0",
        )
    failure = json.loads((output_root / "CERTIFICATION_FAILURE.json").read_text())
    assert failure["status"] == "BLOCKED"
    assert failure["runtime_certified"] is False
    assert (output_root / "SHA256SUMS").is_file()
    assert output_root.with_name("evidence.zip").is_file()

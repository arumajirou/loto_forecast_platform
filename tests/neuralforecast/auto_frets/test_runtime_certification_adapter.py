from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from loto.neuralforecast.auto_frets.runtime_certification import (
    RuntimeSDK,
    build_command_specs,
    build_common_identities,
    build_observation_loader,
)
from loto.neuralforecast.auto_frets.runtime_contracts import (
    AutoFreTSRuntimeRequest,
    AutoFreTSWorkerResponse,
)
from loto.neuralforecast.auto_frets.runtime_source import (
    PreparedSource,
)
from loto.neuralforecast.auto_frets.runtime_worker import (
    _frets_evidence,
    parse_nvidia_smi_output,
    synthetic_values,
)


class Record:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class EvidenceOrigin:
    REAL = "REAL"


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
    statuses = SimpleNamespace(EvidenceOrigin=EvidenceOrigin)
    return RuntimeSDK(
        root=root,
        contracts=contracts,
        statuses=statuses,
        verifier=SimpleNamespace(),
        runner=SimpleNamespace(),
        artifacts=SimpleNamespace(),
    )


def _request(tmp_path: Path, **updates):
    payload = {
        "run_id": "auto-frets-adapter",
        "profile": "CPU_SMOKE",
        "execution_mode": "direct",
        "requested_device": "cpu",
        "source_revision": "a" * 40,
        "source_tree_sha256": "b" * 64,
        "working_directory": str(tmp_path.resolve()),
    }
    payload.update(updates)
    return AutoFreTSRuntimeRequest(**payload)


def test_common_identity_uses_frets_model_and_shape(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path, horizon=3)
    prepared = PreparedSource(
        snapshot_root=tmp_path,
        source_revision="a" * 40,
        source_tree_sha256="b" * 64,
        files=(),
    )
    identities = build_common_identities(
        request,
        prepared_source=prepared,
        sdk=_sdk(),
    )
    assert identities["model"].model_id == "nf-local-auto-frets"
    assert identities["output_contract"].expected_shape == [1, 3]


def test_cpu_commands_hide_cuda_and_use_argv(tmp_path: Path) -> None:
    request = _request(tmp_path)
    first, second = build_command_specs(
        request,
        request_path=tmp_path / "request.json",
        output_root=tmp_path / "output",
        sdk=_sdk(),
        python_executable="/usr/bin/python3",
    )
    assert first.argv[0] == "/usr/bin/python3"
    assert first.argv[2] == ("loto.neuralforecast.auto_frets.runtime_worker")
    assert first.environment["CUDA_VISIBLE_DEVICES"] == ""
    assert second.argv[-1] == "run-b"


def test_observation_loader_maps_cpu_response(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    response = AutoFreTSWorkerResponse(
        status="PASS",
        run_label="run-a",
        execution_mode="direct",
        provider_pid=123,
        package_version="3.2.0",
        source_revision="a" * 40,
        source_tree_sha256="b" * 64,
        requested_device="cpu",
        effective_device="cpu",
        cpu_fallback=False,
        peak_vram_bytes=0,
        output=((1.0,),),
        pre_reload_output=((1.0,),),
        source_verified=True,
        package_verified=True,
        load_success=True,
        input_validation_success=True,
        fit_success=True,
        inference_success=True,
        save_succeeded=True,
        reload_succeeded=True,
        re_predict_succeeded=True,
        auto_backend_executed=False,
        maximum_reload_difference=0.0,
        bundle_path="/tmp/bundle",
        fitted_model_class="FreTS",
        fft_dtype="float32",
        temporal_fft_bins=9,
        channel_frequency_mixing=False,
        parameter_count=590_513,
        expected_parameter_count=590_513,
    )
    path = tmp_path / "output" / "processes" / "run-a" / "WORKER_RESPONSE.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(response.model_dump(mode="json")),
        encoding="utf-8",
    )
    loader = build_observation_loader(
        tmp_path / "output",
        request=request,
        sdk=_sdk(),
    )
    observation = loader("run-a", Record(returncode=0))
    assert observation.output == [[1.0]]
    assert observation.device.cpu_fallback is False


def test_worker_helpers_are_deterministic_and_pid_scoped() -> None:
    assert synthetic_values(5, 1) == synthetic_values(5, 1)
    samples = parse_nvidia_smi_output(
        "123, GPU-abc, 100\n456, GPU-def, 200\n",
        123,
    )
    assert len(samples) == 1
    assert samples[0].used_memory_bytes == 100 * 1024 * 1024


def test_frets_evidence_checks_parameter_formula() -> None:
    import torch

    class Model(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.zeros(3))
            self.loto_model_id = "nf-local-auto-frets"
            self.loto_architecture = {
                "expected_parameter_count": 3,
                "temporal_fft_bins": 9,
            }
            self.loto_fft_dtype = "float32"
            self.loto_channel_frequency_mixing = False

    evidence = _frets_evidence(Model())
    assert evidence["parameter_count"] == 3
    assert evidence["channel_frequency_mixing"] is False

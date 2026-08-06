from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.neuralforecast.auto_timellm.contracts import (
    ArchitectureProfile,
    PinnedLLMIdentity,
    SnapshotFileEvidence,
)
from loto.neuralforecast.auto_timellm.runtime_contracts import (
    AutoTimeLLMRuntimeRequest,
    AutoTimeLLMWorkerResponse,
    canonical_request_sha256,
)
from loto.neuralforecast.auto_timellm.runtime_worker import (
    parse_nvidia_smi_output,
    synthetic_values,
)


def _file(path: Path, relative: str, content: bytes) -> SnapshotFileEvidence:
    target = path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return SnapshotFileEvidence(
        relative_path=relative,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )


def _identity(tmp_path: Path) -> PinnedLLMIdentity:
    revision = "a" * 40
    snapshot = tmp_path / revision
    files = (
        _file(
            snapshot,
            "config.json",
            json.dumps(
                {
                    "model_type": "gpt2",
                    "n_embd": 768,
                    "n_layer": 12,
                    "architectures": ["GPT2Model"],
                }
            ).encode(),
        ),
        _file(snapshot, "tokenizer.json", b"{}"),
        _file(snapshot, "model.safetensors", b"weights"),
    )
    return PinnedLLMIdentity(
        repo_id="openai-community/gpt2",
        revision=revision,
        snapshot_path=str(snapshot.resolve()),
        license_id="MIT",
        files=files,
    )


def _request(tmp_path: Path) -> AutoTimeLLMRuntimeRequest:
    return AutoTimeLLMRuntimeRequest(
        run_id="runtime-test",
        llm_identity=_identity(tmp_path),
        profile="CPU_SMOKE",
        requested_device="cpu",
        architecture_profile=ArchitectureProfile.COMPACT,
        history_length=96,
        working_directory=str(tmp_path.resolve()),
    )


def test_request_hash_is_stable(tmp_path: Path) -> None:
    request = _request(tmp_path)
    assert canonical_request_sha256(request) == canonical_request_sha256(request)
    assert len(canonical_request_sha256(request)) == 64


def test_request_rejects_profile_device_mismatch(tmp_path: Path) -> None:
    request = _request(tmp_path).model_dump()
    request["requested_device"] = "cuda"
    with pytest.raises(ValidationError, match="CPU_SMOKE"):
        AutoTimeLLMRuntimeRequest.model_validate(request)


def test_request_rejects_short_history(tmp_path: Path) -> None:
    request = _request(tmp_path).model_dump()
    request["history_length"] = 16
    with pytest.raises(ValidationError, match="history_length"):
        AutoTimeLLMRuntimeRequest.model_validate(request)


def test_cpu_worker_response_requires_no_gpu_evidence() -> None:
    response = AutoTimeLLMWorkerResponse(
        status="PASS",
        run_label="run-a",
        provider_pid=123,
        package_version="3.2.0",
        requested_device="cpu",
        effective_device="cpu",
        cpu_fallback=False,
        peak_vram_bytes=0,
        output=((1.0,),),
        pre_reload_output=((1.0,),),
        load_success=True,
        input_validation_success=True,
        inference_success=True,
        save_succeeded=True,
        reload_succeeded=True,
        re_predict_succeeded=True,
        maximum_reload_difference=0.0,
        bundle_path="/tmp/bundle",
    )
    assert response.status == "PASS"


def test_worker_response_rejects_non_finite_output() -> None:
    with pytest.raises(ValidationError, match="finite"):
        AutoTimeLLMWorkerResponse(
            status="PASS",
            run_label="run-a",
            provider_pid=123,
            package_version="3.2.0",
            requested_device="cpu",
            effective_device="cpu",
            cpu_fallback=False,
            peak_vram_bytes=0,
            output=((float("nan"),),),
            pre_reload_output=((1.0,),),
            load_success=True,
            input_validation_success=True,
            inference_success=True,
            save_succeeded=True,
            reload_succeeded=True,
            re_predict_succeeded=True,
            maximum_reload_difference=0.0,
            bundle_path="/tmp/bundle",
        )


def test_synthetic_values_are_deterministic() -> None:
    assert synthetic_values(8, 1) == synthetic_values(8, 1)
    assert synthetic_values(8, 1) != synthetic_values(8, 2)
    assert all(1.0 <= value <= 37.0 for value in synthetic_values(64, 1))


def test_nvidia_smi_parser_keeps_only_provider_pid() -> None:
    samples = parse_nvidia_smi_output(
        "123, GPU-aaa, 128\n999, GPU-bbb, 256\ninvalid\n",
        provider_pid=123,
    )
    assert len(samples) == 1
    assert samples[0].provider_pid == 123
    assert samples[0].gpu_uuid == "GPU-aaa"
    assert samples[0].used_memory_bytes == 128 * 1024 * 1024

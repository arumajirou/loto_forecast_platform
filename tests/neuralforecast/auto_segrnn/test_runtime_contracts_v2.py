from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.neuralforecast.auto_segrnn.runtime_contracts import (
    AutoSegRNNRuntimeRequest,
    AutoSegRNNWorkerResponse,
    GPUProcessSampleRecord,
    canonical_request_sha256,
)
from loto.neuralforecast.auto_segrnn.runtime_worker import (
    parse_nvidia_smi_output,
    synthetic_values,
)


def _request(tmp_path: Path, **overrides: object) -> AutoSegRNNRuntimeRequest:
    payload = {
        "run_id": "runtime-contract-test",
        "profile": "CPU_SMOKE",
        "execution_mode": "direct",
        "requested_device": "cpu",
        "source_revision": "a" * 40,
        "source_tree_sha256": "b" * 64,
        "horizon": 1,
        "history_length": 96,
        "working_directory": str(tmp_path.resolve()),
    }
    payload.update(overrides)
    return AutoSegRNNRuntimeRequest.model_validate(payload)


def _cpu_response(**overrides: object) -> AutoSegRNNWorkerResponse:
    payload = {
        "status": "PASS",
        "run_label": "run-a",
        "execution_mode": "direct",
        "provider_pid": 123,
        "package_version": "3.2.0",
        "source_revision": "a" * 40,
        "source_tree_sha256": "b" * 64,
        "requested_device": "cpu",
        "effective_device": "cpu",
        "cpu_fallback": False,
        "peak_vram_bytes": 0,
        "output": ((4.0,),),
        "pre_reload_output": ((4.0,),),
        "source_verified": True,
        "package_verified": True,
        "load_success": True,
        "input_validation_success": True,
        "fit_success": True,
        "inference_success": True,
        "save_succeeded": True,
        "reload_succeeded": True,
        "re_predict_succeeded": True,
        "auto_backend_executed": False,
        "maximum_reload_difference": 0.0,
        "bundle_path": "/tmp/bundle",
        "fitted_model_class": "SegRNN",
    }
    payload.update(overrides)
    return AutoSegRNNWorkerResponse.model_validate(payload)


def test_request_enforces_profile_device_and_precision(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="CPU_SMOKE"):
        _request(tmp_path, requested_device="cuda")
    with pytest.raises(ValidationError, match="precision"):
        _request(tmp_path, precision="16-mixed")
    gpu = _request(
        tmp_path,
        profile="GPU_FORMAL",
        requested_device="cuda",
        precision="16-mixed",
    )
    assert gpu.requested_device == "cuda"


def test_request_rejects_too_short_history(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="history_length"):
        _request(tmp_path, horizon=5, history_length=20)


def test_request_hash_is_canonical(tmp_path: Path) -> None:
    request = _request(tmp_path, execution_mode="ray")
    first = canonical_request_sha256(request)
    second = canonical_request_sha256(
        AutoSegRNNRuntimeRequest.model_validate_json(
            json.dumps(request.model_dump(mode="json"), sort_keys=False)
        )
    )
    assert first == second
    assert len(first) == 64


def test_pass_response_requires_auto_backend_evidence() -> None:
    with pytest.raises(ValidationError, match="backend execution"):
        _cpu_response(execution_mode="ray", auto_backend_executed=False)
    response = _cpu_response(
        execution_mode="optuna",
        auto_backend_executed=True,
        fitted_model_class="AutoSegRNN",
    )
    assert response.execution_mode == "optuna"


def test_cpu_response_rejects_gpu_evidence() -> None:
    with pytest.raises(ValidationError, match="CPU response"):
        _cpu_response(provider_gpu_pid=123, gpu_uuid="GPU-1")


def test_gpu_response_requires_matching_pid_and_memory() -> None:
    sample = GPUProcessSampleRecord(
        provider_pid=123,
        gpu_uuid="GPU-1",
        used_memory_bytes=1024,
        observed_at_utc=datetime.now(UTC),
    )
    response = _cpu_response(
        requested_device="cuda",
        effective_device="cuda",
        provider_gpu_pid=123,
        gpu_uuid="GPU-1",
        peak_vram_bytes=1024,
        external_gpu_samples=(sample,),
    )
    assert response.peak_vram_bytes == 1024


def test_failed_response_requires_structured_error() -> None:
    response = AutoSegRNNWorkerResponse(
        status="FAILED",
        run_label="run-b",
        execution_mode="direct",
        provider_pid=321,
        requested_device="cpu",
        error_type="RuntimeError",
        error_message="dependency unavailable",
    )
    assert response.status == "FAILED"
    with pytest.raises(ValidationError, match="error_type"):
        AutoSegRNNWorkerResponse(
            status="FAILED",
            run_label="run-b",
            execution_mode="direct",
            provider_pid=321,
            requested_device="cpu",
        )


def test_synthetic_values_are_deterministic_and_bounded() -> None:
    first = synthetic_values(20, 1)
    assert first == synthetic_values(20, 1)
    assert first != synthetic_values(20, 2)
    assert min(first) >= 1.0
    assert max(first) <= 37.0


def test_nvidia_smi_parser_keeps_only_matching_positive_pid() -> None:
    text = "123, GPU-1, 256\n999, GPU-2, 512\n123, GPU-1, 0\ninvalid"
    samples = parse_nvidia_smi_output(text, 123)
    assert len(samples) == 1
    assert samples[0].gpu_uuid == "GPU-1"
    assert samples[0].used_memory_bytes == 256 * 1024 * 1024

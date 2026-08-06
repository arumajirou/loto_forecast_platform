from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.adapters.tabpfn_ts import (
    Device,
    GPUEvidence,
    TabPFNTSResponseV2,
    TaskFormulation,
    require_strict_gpu_success,
    validate_local_batch_parity,
)
from .conftest import build_position_response


def test_successful_cuda_response_requires_measured_devices() -> None:
    response = build_position_response(cuda=True)
    require_strict_gpu_success(response.gpu_evidence)
    assert response.gpu_evidence.gpu_uuid == "GPU-test"


def test_cuda_cpu_fallback_is_formal_failure() -> None:
    evidence = GPUEvidence(
        requested_device=Device.CUDA,
        effective_device=Device.CPU,
        model_parameter_device="cpu",
        training_table_device="cpu",
        test_table_device="cpu",
        prediction_tensor_device="cpu",
        provider_pid=123,
        vram_before_bytes=0,
        vram_peak_bytes=0,
        vram_after_bytes=0,
        cpu_fallback=True,
    )
    with pytest.raises(ValueError, match="FAILED_CPU_FALLBACK"):
        require_strict_gpu_success(evidence)


def test_response_rejects_cuda_fallback() -> None:
    payload = build_position_response(cuda=True).model_dump(mode="json")
    payload["gpu_evidence"]["effective_device"] = "cpu"
    payload["gpu_evidence"]["cpu_fallback"] = True
    payload["gpu_evidence"]["model_parameter_device"] = "cpu"
    with pytest.raises(ValidationError, match="FAILED_CPU_FALLBACK"):
        TabPFNTSResponseV2.model_validate(payload)


def test_local_batch_parity_passes_for_identical_outputs() -> None:
    local = build_position_response(task_formulation=TaskFormulation.POSITION_LOCAL)
    batch = build_position_response(task_formulation=TaskFormulation.POSITION_BATCH)
    validate_local_batch_parity(local, batch)


def test_local_batch_parity_rejects_changed_point() -> None:
    local = build_position_response(task_formulation=TaskFormulation.POSITION_LOCAL)
    batch = build_position_response(
        task_formulation=TaskFormulation.POSITION_BATCH,
        point_offset=0.01,
    )
    with pytest.raises(ValueError, match="point parity mismatch"):
        validate_local_batch_parity(local, batch)

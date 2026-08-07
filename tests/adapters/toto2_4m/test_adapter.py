from __future__ import annotations

import numpy as np
import pytest

from loto.adapters.toto2_4m import RuntimeEvidence, Toto2ProviderRequest, Toto2ResponseAdapter
from tests.adapters.toto2_4m.test_contracts import request_payload


def native_output(series: int, horizon: int) -> np.ndarray:
    base = np.arange(series * horizon, dtype=np.float32).reshape(series, horizon)
    return np.stack([base + quantile for quantile in range(9)], axis=0)[:, None, :, :]


def test_adapter_retains_all_native_quantiles() -> None:
    request = Toto2ProviderRequest.model_validate(request_payload())
    evidence = RuntimeEvidence(
        provider_pid=123,
        requested_device="cpu",
        execution_device="cpu",
        model_device="cpu",
        output_device="cpu",
        peak_vram_bytes=0,
        external_gpu_pid_captured=False,
        cpu_fallback=False,
        runtime_scope="CONTRACT_ONLY",
    )
    response = Toto2ResponseAdapter.from_native(
        request,
        native_output(3, 1),
        runtime_evidence=evidence,
        artifact_reference={},
    )
    assert response.status == "OK"
    assert list(response.quantiles) == [f"q{index / 10:.1f}" for index in range(1, 10)]
    assert response.point_forecast == response.quantiles["q0.5"]
    assert response.series_identity == ["p1", "p2", "p3"]
    assert response.effective_arguments["actuals_used"] is False


def test_adapter_rejects_cuda_fallback() -> None:
    payload = request_payload()
    payload["device"] = "cuda"
    request = Toto2ProviderRequest.model_validate(payload)
    evidence = RuntimeEvidence(
        provider_pid=123,
        requested_device="cuda",
        execution_device="cpu",
        model_device="cpu",
        output_device="cpu",
        peak_vram_bytes=0,
        external_gpu_pid_captured=False,
        cpu_fallback=True,
        runtime_scope="FULL_INFERENCE",
    )
    with pytest.raises(ValueError, match="fell back"):
        Toto2ResponseAdapter.from_native(
            request,
            native_output(3, 1),
            runtime_evidence=evidence,
            artifact_reference={},
        )


def test_identity_does_not_claim_runtime_success() -> None:
    response = Toto2ResponseAdapter.identity_response()
    assert response.status == "OK"
    assert response.phase == "identity"
    assert response.runtime_evidence is None
    assert response.model_identity["accuracy_certified"] is False

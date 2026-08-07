from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.neuralforecast.auto_frets.runtime_contracts import (
    AutoFreTSRuntimeRequest,
    AutoFreTSWorkerResponse,
)


def _request(tmp_path: Path, **updates):
    payload = {
        "run_id": "auto-frets-test",
        "profile": "CPU_SMOKE",
        "execution_mode": "direct",
        "requested_device": "cpu",
        "source_revision": "a" * 40,
        "source_tree_sha256": "b" * 64,
        "working_directory": str(tmp_path.resolve()),
    }
    payload.update(updates)
    return AutoFreTSRuntimeRequest(**payload)


def _pass_response(**updates):
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
        "output": ((1.0,),),
        "pre_reload_output": ((1.0,),),
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
        "fitted_model_class": "FreTS",
        "fft_dtype": "float32",
        "temporal_fft_bins": 9,
        "channel_frequency_mixing": False,
        "parameter_count": 590_513,
        "expected_parameter_count": 590_513,
    }
    payload.update(updates)
    return AutoFreTSWorkerResponse(**payload)


def test_request_accepts_strict_cpu_lane(tmp_path: Path) -> None:
    request = _request(tmp_path)
    assert request.precision == "32-true"
    assert request.execution_mode == "direct"


def test_request_rejects_profile_device_mismatch(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="CPU_SMOKE"):
        _request(tmp_path, requested_device="cuda")


def test_request_rejects_short_history(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="history_length"):
        _request(tmp_path, history_length=16, horizon=4)


def test_pass_response_requires_frets_specific_evidence() -> None:
    response = _pass_response()
    assert response.fft_dtype == "float32"
    assert response.channel_frequency_mixing is False


def test_pass_response_rejects_channel_frequency_mixing() -> None:
    with pytest.raises(ValidationError, match="channel mixing"):
        _pass_response(channel_frequency_mixing=True)


def test_pass_response_rejects_parameter_count_drift() -> None:
    with pytest.raises(ValidationError, match="parameter count"):
        _pass_response(parameter_count=590_512)


def test_auto_mode_requires_backend_evidence() -> None:
    with pytest.raises(ValidationError, match="backend execution"):
        _pass_response(execution_mode="ray")

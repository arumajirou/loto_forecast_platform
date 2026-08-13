from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.lightgbm_gpu import probe


def _gpu_snapshot() -> dict[str, object]:
    return {
        "name": "Fake NVIDIA GPU",
        "driver_version": "999.0",
        "memory_total_mib": 16000.0,
        "memory_used_mib": 10.0,
        "memory_free_mib": 15990.0,
        "utilization_percent": 0.0,
        "power_w": 20.0,
    }


def _telemetry() -> dict[str, object]:
    return {
        "samples": 4,
        "baseline_memory_mib": 10.0,
        "max_memory_mib": 128.0,
        "memory_delta_mib": 118.0,
        "max_util_percent": 25.0,
        "max_power_w": 60.0,
    }


def test_candidate_device_types_prefers_cuda_then_opencl_gpu() -> None:
    assert probe.candidate_device_types("auto") == ("cuda", "gpu")
    assert probe.candidate_device_types("cuda") == ("cuda",)
    assert probe.candidate_device_types("gpu") == ("gpu",)

    with pytest.raises(ValueError):
        probe.candidate_device_types("cpu")


def test_gpu_activity_accepts_utilization_or_memory_growth() -> None:
    assert probe.gpu_activity_evidence(
        baseline_memory_mib=10.0,
        max_memory_mib=10.0,
        max_util_percent=1.0,
        min_memory_delta_mib=32.0,
    )
    assert probe.gpu_activity_evidence(
        baseline_memory_mib=10.0,
        max_memory_mib=50.0,
        max_util_percent=0.0,
        min_memory_delta_mib=32.0,
    )
    assert not probe.gpu_activity_evidence(
        baseline_memory_mib=10.0,
        max_memory_mib=20.0,
        max_util_percent=0.0,
        min_memory_delta_mib=32.0,
    )


def test_probe_fails_closed_without_nvidia_gpu(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(probe, "_nvidia_snapshot", lambda: None)
    output = tmp_path / "probe"

    result = probe.run_probe(
        output=output,
        requested_device_type="auto",
        rows=100,
        features=4,
        rounds=2,
        seed=1,
        telemetry_interval=0.01,
        min_memory_delta_mib=32.0,
    )

    assert result["status"] == "BLOCKED_NO_NVIDIA_GPU"
    persisted = json.loads((output / "CERTIFICATION.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "BLOCKED_NO_NVIDIA_GPU"


def test_probe_selects_cuda_when_fit_and_external_activity_pass(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(probe, "_nvidia_snapshot", _gpu_snapshot)
    monkeypatch.setattr(probe, "_telemetry_worker", lambda *args, **kwargs: None)
    monkeypatch.setattr(probe, "_telemetry_summary", lambda *args, **kwargs: _telemetry())
    monkeypatch.setattr(
        probe,
        "_fit_lightgbm",
        lambda **kwargs: {
            "lightgbm_version": "test",
            "classifier_finite": True,
            "regressor_finite": True,
        },
    )

    result = probe.run_probe(
        output=tmp_path / "probe",
        requested_device_type="auto",
        rows=100,
        features=4,
        rounds=2,
        seed=1,
        telemetry_interval=0.01,
        min_memory_delta_mib=32.0,
    )

    assert result["status"] == "VERIFIED"
    assert result["selected_device_type"] == "cuda"
    assert result["attempts"][0]["status"] == "VERIFIED"


def test_probe_falls_back_to_opencl_gpu_when_cuda_build_is_unavailable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(probe, "_nvidia_snapshot", _gpu_snapshot)
    monkeypatch.setattr(probe, "_telemetry_worker", lambda *args, **kwargs: None)
    monkeypatch.setattr(probe, "_telemetry_summary", lambda *args, **kwargs: _telemetry())

    def fake_fit(**kwargs):
        if kwargs["device_type"] == "cuda":
            raise RuntimeError("CUDA Tree Learner was not enabled in this build")
        return {
            "lightgbm_version": "test",
            "classifier_finite": True,
            "regressor_finite": True,
        }

    monkeypatch.setattr(probe, "_fit_lightgbm", fake_fit)

    result = probe.run_probe(
        output=tmp_path / "probe",
        requested_device_type="auto",
        rows=100,
        features=4,
        rounds=2,
        seed=1,
        telemetry_interval=0.01,
        min_memory_delta_mib=32.0,
    )

    assert result["status"] == "VERIFIED"
    assert result["selected_device_type"] == "gpu"
    assert result["attempts"][0]["status"] == "UNSUPPORTED_OR_FAILED"
    assert result["attempts"][1]["status"] == "VERIFIED"

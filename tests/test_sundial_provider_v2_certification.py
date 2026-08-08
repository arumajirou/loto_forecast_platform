from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_harness() -> ModuleType:
    path = ROOT / "scripts" / "certify_sundial_provider_v2.py"
    spec = importlib.util.spec_from_file_location("sundial_provider_v2_certification", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


HARNESS = _load_harness()


def _response(device: str = "cuda", num_samples: int = 3) -> dict[str, Any]:
    return {
        "status": "OK",
        "provider_version": 2,
        "samples_shape": [7, num_samples, 1],
        "samples": [
            [[float(series + sample)] for sample in range(num_samples)] for series in range(7)
        ],
        "predictions": [float(index) for index in range(7)],
        "quantile_source": "EMPIRICAL_FROM_GENERATED_SAMPLES",
        "gpu_evidence": {
            "execution_device": device,
            "gpu_used": device == "cuda",
            "cpu_fallback": False,
            "peak_vram_bytes": 1 if device == "cuda" else 0,
            "gpu_pid": 123,
        },
    }


def test_parse_counts_rejects_duplicates_and_out_of_range() -> None:
    assert HARNESS.parse_counts("1,3,20") == (1, 3, 20)
    with pytest.raises(argparse.ArgumentTypeError):
        HARNESS.parse_counts("1,1")
    with pytest.raises(argparse.ArgumentTypeError):
        HARNESS.parse_counts("0")


def test_cuda_validation_requires_external_pid_and_vram() -> None:
    reasons = HARNESS.validate_response(
        _response(),
        pid=123,
        device="cuda",
        num_samples=3,
        external_seen=True,
        external_peak_mib=512,
    )
    assert reasons == []

    reasons = HARNESS.validate_response(
        _response(),
        pid=123,
        device="cuda",
        num_samples=3,
        external_seen=False,
        external_peak_mib=0,
    )
    assert "EXTERNAL_GPU_PID_NOT_SEEN" in reasons
    assert "EXTERNAL_VRAM_NOT_OBSERVED" in reasons


def test_cpu_validation_rejects_gpu_use() -> None:
    response = _response(device="cpu", num_samples=1)
    assert (
        HARNESS.validate_response(
            response,
            pid=123,
            device="cpu",
            num_samples=1,
            external_seen=False,
            external_peak_mib=0,
        )
        == []
    )

    response["gpu_evidence"]["gpu_used"] = True
    reasons = HARNESS.validate_response(
        response,
        pid=123,
        device="cpu",
        num_samples=1,
        external_seen=False,
        external_peak_mib=0,
    )
    assert "CPU_SMOKE_DEVICE_MISMATCH" in reasons


def test_replay_classification_exact_close_and_divergent() -> None:
    exact = HARNESS.compare_replays(
        {"samples": [1.0, 2.0]},
        {"samples": [1.0, 2.0]},
    )
    assert exact["classification"] == "EXACT"
    assert exact["passed"] is True

    close = HARNESS.compare_replays(
        {"samples": [1.0, 2.0]},
        {"samples": [1.0 + 1e-8, 2.0]},
    )
    assert close["classification"] == "NUMERIC_CLOSE"
    assert close["passed"] is True

    divergent = HARNESS.compare_replays(
        {"samples": [1.0, 2.0]},
        {"samples": [1.5, 2.0]},
    )
    assert divergent["classification"] == "DIVERGENT"
    assert divergent["passed"] is False


def test_invalid_json_is_classified_as_certification_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(HARNESS.CertificationError):
        HARNESS.load_json(path)

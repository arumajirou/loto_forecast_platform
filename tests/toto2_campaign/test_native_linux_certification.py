from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from loto.toto2_campaign.variant_probe import VariantProbeError

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/certify_toto2_22m_native_linux.py"
SPEC = importlib.util.spec_from_file_location("native_cert", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
build_certification = MODULE.build_certification


def probe(pid: int) -> dict[str, object]:
    return {
        "status": "PASS",
        "pid": pid,
        "revision": "revision",
        "snapshot": {"files": {"model.safetensors": {"sha256": "abc"}}},
        "model_identity": {
            "parameter_count": 21_915_584,
            "model_class": "Toto2Model",
            "patch_size": 32,
            "quantile_levels": [0.1, 0.2],
        },
        "device": {
            "gpu_uuid": "GPU-a",
            "external_gpu_pid_captured": True,
            "nvidia_smi_used_gpu_memory_mib": 145,
            "peak_vram_bytes": 1000,
            "cpu_fallback": False,
        },
        "native_output_sha256": "same",
        "certification_blockers": [],
    }


def release(pid: int, *, certified: bool = True) -> dict[str, object]:
    return {
        "pid": pid,
        "process_exited": certified,
        "external_gpu_pid_absent": certified,
        "post_exit_gpu_release_certified": certified,
    }


def test_build_certification_requires_complete_native_evidence() -> None:
    output = np.array([1.0, 2.0], dtype=np.float32)
    result = build_certification(
        first=probe(101),
        second=probe(202),
        release_1=release(101),
        release_2=release(202),
        output_1=output,
        output_2=output.copy(),
    )
    assert result["status"] == "PASS"
    assert result["formal_runtime_certified"] is True
    assert result["manifest_runtime_certified_update_allowed"] is True
    assert result["shared_routing_allowed"] is False


def test_build_certification_rejects_missing_post_exit_release() -> None:
    output = np.array([1.0, 2.0], dtype=np.float32)
    with pytest.raises(VariantProbeError, match="post-exit GPU release"):
        build_certification(
            first=probe(101),
            second=probe(202),
            release_1=release(101, certified=False),
            release_2=release(202),
            output_1=output,
            output_2=output.copy(),
        )


def test_build_certification_rejects_partial_probe() -> None:
    first = probe(101)
    first["status"] = "PARTIAL_PASS"
    output = np.array([1.0, 2.0], dtype=np.float32)
    with pytest.raises(VariantProbeError, match="must be PASS"):
        build_certification(
            first=first,
            second=probe(202),
            release_1=release(101),
            release_2=release(202),
            output_1=output,
            output_2=output.copy(),
        )

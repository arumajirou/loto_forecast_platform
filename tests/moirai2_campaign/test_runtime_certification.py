from __future__ import annotations

from copy import deepcopy

import pytest

from loto.moirai2_campaign.runtime_certification import (
    ComputeProcessRecord,
    GpuMemoryRecord,
    RuntimeCertificationError,
    certify_external_gpu_evidence,
    compare_provider_responses,
    parse_compute_process_csv,
    parse_gpu_memory_csv,
    sha256_payload,
    validate_provider_device_evidence,
)


def _response(*, pid: int, device: str = "cpu") -> dict:
    return {
        "status": "OK",
        "model_identity": {
            "model_id": "moirai-2.0-r-small",
            "revision": "revision",
        },
        "point_forecast": [[1.0, 2.0]],
        "quantiles": {
            f"{level:.1f}": [[level, level + 1.0]]
            for level in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
        },
        "series_identity": ["n1", "n2"],
        "prediction_index": [1],
        "artifact_reference": {
            "model_revision": "revision",
            "config_sha256": "a" * 64,
            "weight_sha256": "b" * 64,
        },
        "covariate_evidence": {
            "past": {"names": ["frequency"], "shape": [1, 16], "sha256": "c" * 64},
            "known_future": {
                "names": ["weekday"],
                "shape": [1, 17],
                "sha256": "d" * 64,
            },
            "known_future_tail_sha256": "e" * 64,
            "chronology_valid": True,
            "availability_verified": True,
            "actuals_used": False,
        },
        "runtime_evidence": {
            "process_id": pid,
            "package_version": "2.0.0",
            "runtime_lane": "supported-py311",
            "requested_device": device,
            "execution_device": device,
            "model_parameter_device": device,
            "output_shape": [1, 2],
            "all_quantiles_finite": True,
            "quantile_monotonicity": True,
            "cpu_fallback": False,
        },
        "effective_arguments": {
            "predictor_device": device,
            "forward_device_evidence": {
                "input_tensor_devices": [device],
                "output_tensor_devices": [device],
                "forward_call_count": 1,
            },
        },
        "gpu_evidence": {
            "requested_device": device,
            "execution_device": device,
            "cuda_available": device == "cuda",
            "provider_pid": pid,
            "gpu_pid": pid if device == "cuda" else None,
            "peak_vram_bytes": 1024 if device == "cuda" else 0,
            "cpu_fallback": False,
        },
    }


def test_csv_parsers_are_strict() -> None:
    assert parse_compute_process_csv("123, GPU-abc, 81\n") == [
        ComputeProcessRecord(pid=123, gpu_uuid="GPU-abc", used_memory_mib=81)
    ]
    assert parse_gpu_memory_csv("GPU-abc, 901\n") == [
        GpuMemoryRecord(gpu_uuid="GPU-abc", used_memory_mib=901)
    ]
    with pytest.raises(RuntimeCertificationError, match="invalid compute-process row"):
        parse_compute_process_csv("broken")


def test_separate_process_responses_require_exact_prediction_hash() -> None:
    first = _response(pid=100)
    second = _response(pid=101)
    comparison = compare_provider_responses(first, second)
    assert comparison.distinct_processes is True
    assert comparison.exact_prediction_match is True
    assert comparison.maximum_absolute_difference == 0.0
    assert comparison.prediction_sha256_a == comparison.prediction_sha256_b


def test_reload_rejects_same_pid_and_changed_quantile() -> None:
    first = _response(pid=100)
    with pytest.raises(RuntimeCertificationError, match="distinct process"):
        compare_provider_responses(first, deepcopy(first))
    second = _response(pid=101)
    second["quantiles"]["0.9"][0][0] += 0.001
    with pytest.raises(RuntimeCertificationError, match="SHA-256"):
        compare_provider_responses(first, second)


def test_device_evidence_rejects_missing_forward_observation() -> None:
    response = _response(pid=100)
    response["effective_arguments"]["forward_device_evidence"]["forward_call_count"] = 0
    with pytest.raises(RuntimeCertificationError, match="no model forward"):
        validate_provider_device_evidence(response)


def test_external_cuda_certification_requires_pid_match_and_release() -> None:
    response = _response(pid=700, device="cuda")
    evidence = certify_external_gpu_evidence(
        response=response,
        samples=[ComputeProcessRecord(700, "GPU-1", 80)],
        before_memory=[GpuMemoryRecord("GPU-1", 100)],
        after_memory=[GpuMemoryRecord("GPU-1", 101)],
        after_processes=[],
    )
    assert evidence.external_pid_match is True
    assert evidence.gpu_uuid == "GPU-1"
    assert evidence.peak_process_memory_mib == 80
    assert evidence.pid_absent_after_exit is True
    with pytest.raises(RuntimeCertificationError, match="never observed"):
        certify_external_gpu_evidence(
            response=response,
            samples=[],
            before_memory=[],
            after_memory=[],
            after_processes=[],
        )


def test_cpu_certification_rejects_external_gpu_presence() -> None:
    response = _response(pid=701, device="cpu")
    evidence = certify_external_gpu_evidence(
        response=response,
        samples=[],
        before_memory=[],
        after_memory=[],
        after_processes=[],
    )
    assert evidence.requested_device == "cpu"
    with pytest.raises(RuntimeCertificationError, match="CPU run appeared"):
        certify_external_gpu_evidence(
            response=response,
            samples=[ComputeProcessRecord(701, "GPU-1", 10)],
            before_memory=[],
            after_memory=[],
            after_processes=[],
        )


def test_prediction_hash_is_canonical() -> None:
    assert sha256_payload({"b": 2, "a": 1}) == sha256_payload({"a": 1, "b": 2})


def test_sha256_manifest_excludes_itself(tmp_path) -> None:
    from loto.moirai2_campaign.runtime_certification import write_sha256_manifest

    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    manifest = tmp_path / "SHA256SUMS"
    write_sha256_manifest(tmp_path, manifest)
    text = manifest.read_text(encoding="utf-8")
    assert "a.txt" in text
    assert "SHA256SUMS" not in text


def test_cuda_device_mismatch_fails_closed() -> None:
    response = _response(pid=902, device="cuda")
    response["effective_arguments"]["forward_device_evidence"][
        "input_tensor_devices"
    ] = ["cpu"]
    with pytest.raises(RuntimeCertificationError, match="does not stay on cuda"):
        validate_provider_device_evidence(response)

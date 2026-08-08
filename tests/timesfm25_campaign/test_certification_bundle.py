from __future__ import annotations

import json
from pathlib import Path

import pytest

from loto.adapters.timesfm25.contracts import (
    ArtifactReference,
    Backend,
    GameGeometry,
    GPUExecutionEvidence,
    ModelIdentity,
    RuntimeEvidence,
    TimesFM25Request,
    TimesFM25Response,
)
from loto.timesfm25_campaign.certification_bundle import (
    atomic_write_json,
    build_certification_report,
    validate_run_id,
    verify_sha256_manifest,
    write_sha256_manifest,
)


def _request(device: str = "cuda") -> TimesFM25Request:
    return TimesFM25Request(
        run_id="timesfm25-test",
        backend=Backend.PYTORCH_NATIVE,
        repo_id="google/timesfm-2.5-200m-pytorch",
        revision="1d952420fba87f3c6dee4f240de0f1a0fbc790e3",
        game_geometry=GameGeometry(
            game_id="numbers3",
            position_count=3,
            candidate_min=0,
            candidate_max=9,
        ),
        series_ids=["n1", "n2", "n3"],
        history={"n1": [1.0] * 8, "n2": [2.0] * 8, "n3": [3.0] * 8},
        context_length=8,
        prediction_length=1,
        device=device,
    )


def _response(*, requested: bool, cuda_outputs: bool) -> TimesFM25Response:
    output_device = "cuda:0" if cuda_outputs else "cpu_numpy"
    quantiles = {f"0.{index}": [[float(index)] for _ in range(3)] for index in range(1, 10)}
    return TimesFM25Response(
        model_identity=ModelIdentity(
            backend=Backend.PYTORCH_NATIVE,
            checkpoint_repo_id="google/timesfm-2.5-200m-pytorch",
            checkpoint_revision="1d952420fba87f3c6dee4f240de0f1a0fbc790e3",
            package_version="2.0.2",
        ),
        effective_arguments={},
        median_forecast=[[5.0], [5.0], [5.0]],
        mean_forecast=[[5.5], [5.5], [5.5]],
        quantiles=quantiles,
        series_identity=["n1", "n2", "n3"],
        prediction_index=[0],
        runtime_evidence=RuntimeEvidence(
            provider_pid=123,
            model_parameter_device="cuda:0" if requested else "cpu",
            input_device="cpu_numpy_staging",
            mean_output_device=output_device,
            quantile_output_device=output_device,
            cpu_fallback=False,
            load_time_seconds=1.0,
            compile_time_seconds=0.5,
            inference_time_seconds=0.1,
            compile_requested=False,
            compile_effective=False,
        ),
        gpu_evidence=GPUExecutionEvidence(
            requested=requested,
            cuda_available=requested,
            gpu_used=requested,
            provider_pid=123,
            external_pid_match=requested,
            gpu_uuid="GPU-test" if requested else None,
            vram_before_bytes=0,
            vram_peak_bytes=1024 if requested else 0,
            vram_after_bytes=0,
            cpu_fallback=False,
            certification_status="PARTIAL" if requested else "NOT_REQUESTED",
        ),
        artifact_reference=ArtifactReference(
            repo_id="google/timesfm-2.5-200m-pytorch",
            revision="1d952420fba87f3c6dee4f240de0f1a0fbc790e3",
            snapshot_path="/tmp/snapshot",
        ),
    )


@pytest.mark.parametrize("value", ["run-1", "timesfm25.test_01", "A"])
def test_validate_run_id_accepts_safe_values(value: str) -> None:
    assert validate_run_id(value) == value


@pytest.mark.parametrize("value", ["../escape", "/absolute", "", ".", "..", "white space"])
def test_validate_run_id_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError):
        validate_run_id(value)


def test_bundle_manifest_detects_tampering(tmp_path: Path) -> None:
    atomic_write_json(tmp_path / "result.json", {"status": "OK"})
    manifest = write_sha256_manifest(tmp_path)

    ok, failures = verify_sha256_manifest(tmp_path)
    assert ok is True
    assert failures == ()

    (tmp_path / "result.json").write_text(json.dumps({"status": "changed"}), encoding="utf-8")
    ok, failures = verify_sha256_manifest(tmp_path)
    assert ok is False
    assert failures == ("result.json:HASH_MISMATCH",)
    assert manifest.name == "SHA256SUMS"

    atomic_write_json(tmp_path / "unexpected.json", {"new": True})
    ok, failures = verify_sha256_manifest(tmp_path)
    assert ok is False
    assert "unexpected.json:UNEXPECTED" in failures


def test_report_marks_native_numpy_outputs_partial() -> None:
    report = build_certification_report(
        _request(),
        _response(requested=True, cuda_outputs=False).model_dump(mode="json"),
        provider_exit_code=0,
        timed_out=False,
    )

    assert report["runtime_status"] == "PARTIALLY_VERIFIED_GPU"
    assert report["gpu_certification_status"] == "FAIL"
    assert report["gpu_certification_reasons"] == [
        "MEAN_OUTPUT_NOT_CUDA",
        "QUANTILE_OUTPUT_NOT_CUDA",
    ]


def test_report_accepts_cpu_runtime_without_gpu_claim() -> None:
    report = build_certification_report(
        _request(device="cpu"),
        _response(requested=False, cuda_outputs=False).model_dump(mode="json"),
        provider_exit_code=0,
        timed_out=False,
    )

    assert report["runtime_status"] == "VERIFIED_CPU"
    assert report["gpu_certification_status"] == "NOT_REQUESTED"


def test_report_accepts_strict_cuda_evidence() -> None:
    report = build_certification_report(
        _request(),
        _response(requested=True, cuda_outputs=True).model_dump(mode="json"),
        provider_exit_code=0,
        timed_out=False,
    )

    assert report["runtime_status"] == "VERIFIED_GPU"
    assert report["gpu_certification_status"] == "PASS"


def test_report_distinguishes_timeout_and_provider_error() -> None:
    timeout_report = build_certification_report(
        _request(),
        None,
        provider_exit_code=124,
        timed_out=True,
    )
    error_report = build_certification_report(
        _request(),
        {"status": "ERROR", "message": "weights missing", "error_type": "FileNotFoundError"},
        provider_exit_code=0,
        timed_out=False,
    )

    assert timeout_report["failure_reason"] == "PROVIDER_TIMEOUT"
    assert error_report["failure_reason"] == "weights missing"
    assert error_report["provider_error_type"] == "FileNotFoundError"

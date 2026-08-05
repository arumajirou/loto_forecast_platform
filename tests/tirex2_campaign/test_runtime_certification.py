from __future__ import annotations

from loto.adapters.tirex2.contracts import (
    ArtifactReference,
    GpuEvidence,
    ModelIdentity,
    RuntimeEvidence,
    Tirex2Response,
)
from loto.tirex2_campaign.runtime_certification import (
    ProcessRunEvidence,
    compare_responses,
)


def _response(pid: int, point: float = 5.0) -> Tirex2Response:
    quantiles = {
        f"{level / 10:.1f}": [[float(level)]] for level in range(1, 10)
    }
    quantiles["0.5"] = [[point]]
    for level in range(6, 10):
        quantiles[f"{level / 10:.1f}"] = [[point + level - 5]]
    return Tirex2Response(
        run_id="certification-test",
        model_identity=ModelIdentity(
            weight_sha256="a" * 64,
            config_sha256="b" * 64,
        ),
        effective_arguments={},
        point_forecast=[[point]],
        quantiles=quantiles,
        series_identity=["n1"],
        prediction_index=[1],
        runtime_evidence=RuntimeEvidence(
            provider_pid=pid,
            requested_device="cpu",
            effective_device="cpu",
            model_parameter_device="cpu",
            target_tensor_device="cpu",
            past_covariate_device=None,
            future_covariate_device=None,
            output_tensor_device=None,
            dtype="float32",
            cpu_fallback=False,
            load_time_seconds=0.1,
            inference_time_seconds=0.2,
        ),
        gpu_evidence=GpuEvidence(
            vram_before_bytes=0,
            vram_peak_bytes=0,
            vram_after_bytes=0,
        ),
        artifact_reference=ArtifactReference(snapshot_path="/trusted/snapshot"),
    )


def _evidence(label: str, pid: int) -> ProcessRunEvidence:
    return ProcessRunEvidence(
        label=label,
        provider_pid=pid,
        exit_code=0,
        response_path=f"{label}/response.json",
        stdout_path=f"{label}/stdout.log",
        stderr_path=f"{label}/stderr.log",
        response_sha256="c" * 64,
    )


def test_compare_responses_accepts_distinct_process_exact_reproduction() -> None:
    result = compare_responses(
        _response(101),
        _response(202),
        run_a=_evidence("run-a", 101),
        run_b=_evidence("run-b", 202),
    )
    assert result.status == "PASS"
    assert result.distinct_provider_pids is True
    assert result.all_quantiles_match is True


def test_compare_responses_rejects_same_process() -> None:
    result = compare_responses(
        _response(101),
        _response(101),
        run_a=_evidence("run-a", 101),
        run_b=_evidence("run-b", 101),
    )
    assert result.status == "FAIL"
    assert "distinct_provider_pids" in result.blockers


def test_compare_responses_rejects_prediction_drift() -> None:
    result = compare_responses(
        _response(101, point=5.0),
        _response(202, point=5.5),
        run_a=_evidence("run-a", 101),
        run_b=_evidence("run-b", 202),
    )
    assert result.status == "FAIL"
    assert "point_forecast_match" in result.blockers
    assert "all_quantiles_match" in result.blockers

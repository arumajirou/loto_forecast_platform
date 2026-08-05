from __future__ import annotations

from loto.adapters.timesfm25.adapter import downgrade_v2_response, upgrade_v1_request
from loto.adapters.timesfm25.contracts import (
    ArtifactReference,
    Backend,
    GPUExecutionEvidence,
    ModelIdentity,
    RuntimeEvidence,
    TimesFM25Response,
)


def _response(horizon: int) -> TimesFM25Response:
    rows = [[float(step + 1) for step in range(horizon)] for _ in range(3)]
    return TimesFM25Response(
        model_identity=ModelIdentity(
            backend=Backend.PYTORCH_NATIVE,
            checkpoint_repo_id="google/timesfm-2.5-200m-pytorch",
            checkpoint_revision="1d952420fba87f3c6dee4f240de0f1a0fbc790e3",
            package_version="2.0.2",
        ),
        effective_arguments={},
        median_forecast=rows,
        mean_forecast=rows,
        quantiles={f"0.{index}": rows for index in range(1, 10)},
        series_identity=["n1", "n2", "n3"],
        prediction_index=list(range(horizon)),
        runtime_evidence=RuntimeEvidence(
            provider_pid=1,
            model_parameter_device="cpu",
            input_device="cpu_numpy_staging",
            mean_output_device="cpu_numpy",
            quantile_output_device="cpu_numpy",
            cpu_fallback=False,
            load_time_seconds=0,
            compile_time_seconds=0,
            inference_time_seconds=0,
            compile_requested=False,
            compile_effective=False,
        ),
        gpu_evidence=GPUExecutionEvidence(
            requested=False,
            cuda_available=False,
            gpu_used=False,
            provider_pid=1,
            external_pid_match=False,
            vram_before_bytes=0,
            vram_peak_bytes=0,
            vram_after_bytes=0,
            cpu_fallback=False,
            certification_status="NOT_REQUESTED",
        ),
        artifact_reference=ArtifactReference(
            repo_id="google/timesfm-2.5-200m-pytorch",
            revision="1d952420fba87f3c6dee4f240de0f1a0fbc790e3",
            snapshot_path="/tmp/snapshot",
        ),
    )


def test_schema_v1_request_upgrade_is_dynamic() -> None:
    request = upgrade_v1_request(
        {
            "schema_version": 1,
            "history": [
                {"n1": 1, "n2": 2, "n3": 3, "n4": 4},
                {"n1": 2, "n2": 3, "n3": 4, "n4": 5},
            ],
            "prediction_length": 2,
        }
    )
    assert request.backend == Backend.PYTORCH_NATIVE
    assert request.series_ids == ["n1", "n2", "n3", "n4"]
    assert request.prediction_length == 2


def test_schema_v2_response_downgrade_uses_first_horizon_only_for_v1() -> None:
    response = downgrade_v2_response(_response(horizon=2))
    assert response["prediction_shape"] == [3]
    assert response["properties"]["prediction_length"] == 2

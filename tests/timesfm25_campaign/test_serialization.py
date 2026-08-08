from __future__ import annotations

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
from loto.timesfm25_campaign.serialization import verify_separate_process_reload


def _request() -> TimesFM25Request:
    return TimesFM25Request(
        run_id="reload-test",
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
        history={"n1": [1.0], "n2": [2.0], "n3": [3.0]},
        context_length=1,
        prediction_length=1,
    )


def _response(reloaded: bool) -> TimesFM25Response:
    rows = [[1.0], [2.0], [3.0]]
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
        prediction_index=[0],
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
            snapshot_path="/tmp/pinned-snapshot",
            snapshot_reloaded=reloaded,
        ),
    )


def test_reload_verifier_runs_predict_then_reload_predict() -> None:
    operations: list[tuple[str, str | None]] = []

    def execute(request: TimesFM25Request) -> TimesFM25Response:
        operations.append((request.operation, request.snapshot_path))
        return _response(reloaded=request.operation == "reload_predict")

    verdict = verify_separate_process_reload(execute, _request())
    assert verdict.status == "PASS"
    assert operations == [
        ("predict", None),
        ("reload_predict", "/tmp/pinned-snapshot"),
    ]

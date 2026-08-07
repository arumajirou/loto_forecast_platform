from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.adapters.timesfm25.contracts import (
    ArtifactReference,
    Backend,
    GPUExecutionEvidence,
    GameGeometry,
    ModelIdentity,
    RuntimeEvidence,
    TimesFM25Request,
    TimesFM25Response,
)


def make_request(position_count: int = 3, horizon: int = 1) -> TimesFM25Request:
    ids = [f"n{index}" for index in range(1, position_count + 1)]
    return TimesFM25Request(
        run_id="test-run",
        backend=Backend.PYTORCH_NATIVE,
        repo_id="google/timesfm-2.5-200m-pytorch",
        revision="1d952420fba87f3c6dee4f240de0f1a0fbc790e3",
        game_geometry=GameGeometry(
            game_id="numbers3",
            position_count=position_count,
            candidate_min=0,
            candidate_max=9,
        ),
        series_ids=ids,
        history={series_id: [1.0, 2.0, 3.0] for series_id in ids},
        context_length=3,
        prediction_length=horizon,
    )


def make_response(horizon: int = 2) -> TimesFM25Response:
    rows = [[float(step + 1) for step in range(horizon)] for _ in range(3)]
    quantiles = {f"0.{index}": rows for index in range(1, 10)}
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
        quantiles=quantiles,
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


@pytest.mark.parametrize("position_count", [3, 4, 5, 6, 7])
def test_arbitrary_series_count(position_count: int) -> None:
    assert len(make_request(position_count=position_count).series_ids) == position_count


@pytest.mark.parametrize("horizon", [1, 2, 5])
def test_formal_horizons(horizon: int) -> None:
    assert make_request(horizon=horizon).prediction_length == horizon


def test_unknown_request_key_is_rejected() -> None:
    payload = make_request().model_dump()
    payload["unknown"] = True
    with pytest.raises(ValidationError):
        TimesFM25Request.model_validate(payload)


def test_history_keys_must_match_series_ids() -> None:
    payload = make_request().model_dump()
    payload["history"].pop("n3")
    with pytest.raises(ValidationError):
        TimesFM25Request.model_validate(payload)


def test_response_preserves_full_horizon() -> None:
    response = make_response(horizon=5)
    assert len(response.median_forecast[0]) == 5
    assert len(response.quantiles) == 9


def test_quantile_crossing_is_rejected() -> None:
    payload = make_response().model_dump()
    payload["quantiles"]["0.1"][0][0] = 10
    with pytest.raises(ValidationError):
        TimesFM25Response.model_validate(payload)

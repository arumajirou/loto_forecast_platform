from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from loto.adapters.tirex2.compat import schema_v1_to_v2
from loto.adapters.tirex2.contracts import (
    ArtifactReference,
    CovariateBlock,
    GameGeometry,
    GpuEvidence,
    ModelIdentity,
    RuntimeEvidence,
    SeriesLayout,
    Tirex2Request,
    Tirex2Response,
)

ISSUE_TIME = datetime(2026, 8, 6, tzinfo=UTC)


def request_payload(position_count: int = 3, horizon: int = 1) -> dict[str, object]:
    return {
        "schema_version": 2,
        "run_id": "test-run",
        "game_geometry": {
            "game_id": "numbers3",
            "position_count": position_count,
            "candidate_min": 0,
            "candidate_max": 9,
            "strictly_increasing": False,
        },
        "series_layout": "position_joint_multivariate",
        "target_columns": [f"n{index}" for index in range(1, position_count + 1)],
        "target_history": [[float(index), float(index + 1)] for index in range(position_count)],
        "prediction_issue_time": ISSUE_TIME.isoformat(),
        "context_length": 2,
        "prediction_length": horizon,
    }


@pytest.mark.parametrize("position_count", [1, 3, 4, 5, 6, 7])
@pytest.mark.parametrize("horizon", [1, 2, 5])
def test_request_supports_arbitrary_target_count_and_horizon(
    position_count: int, horizon: int
) -> None:
    payload = request_payload(position_count, horizon)
    if position_count == 1:
        payload["series_layout"] = "position_local"
    request = Tirex2Request.model_validate(payload)
    assert len(request.target_columns) == position_count
    assert request.prediction_length == horizon


def test_unknown_keys_are_rejected() -> None:
    payload = request_payload()
    payload["unknown"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Tirex2Request.model_validate(payload)


def test_future_covariate_must_be_known_at_prediction_time() -> None:
    payload = request_payload(horizon=2)
    payload["future_covariates"] = {
        "names": ["draw_no"],
        "values": [[1.0, 2.0]],
        "known_at_prediction_time": False,
    }
    with pytest.raises(ValidationError, match="known at prediction time"):
        Tirex2Request.model_validate(payload)


def test_future_covariate_source_time_is_fail_closed() -> None:
    payload = request_payload()
    payload["future_covariates"] = {
        "names": ["draw_no"],
        "values": [[1.0]],
        "source_timestamps": [(ISSUE_TIME + timedelta(seconds=1)).isoformat()],
        "known_at_prediction_time": True,
    }
    with pytest.raises(ValidationError, match="source timestamps"):
        Tirex2Request.model_validate(payload)


def test_position_local_rejects_multiple_targets() -> None:
    payload = request_payload(position_count=3)
    payload["series_layout"] = SeriesLayout.POSITION_LOCAL.value
    with pytest.raises(ValidationError, match="exactly one target"):
        Tirex2Request.model_validate(payload)


def test_schema_v1_adapter_is_explicitly_seven_position_only() -> None:
    legacy = {
        "history": [{f"n{index}": float(index) for index in range(1, 8)} for _ in range(3)],
        "prediction_length": 1,
    }
    converted = schema_v1_to_v2(legacy)
    assert converted.schema_version == 2
    assert converted.game_geometry.position_count == 7
    assert converted.context_length == 3


def valid_response() -> Tirex2Response:
    quantiles = {
        f"{level / 10:.1f}": [[float(level), float(level + 1)]] for level in range(1, 10)
    }
    return Tirex2Response(
        run_id="test-run",
        model_identity=ModelIdentity(
            weight_sha256="a" * 64,
            config_sha256="b" * 64,
        ),
        effective_arguments={},
        point_forecast=quantiles["0.5"],
        quantiles=quantiles,
        series_identity=["n1"],
        prediction_index=[1, 2],
        runtime_evidence=RuntimeEvidence(
            provider_pid=1,
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


def test_response_preserves_all_quantiles_and_q05_identity() -> None:
    response = valid_response()
    assert list(response.quantiles) == [f"{level / 10:.1f}" for level in range(1, 10)]
    assert response.point_forecast == response.quantiles["0.5"]


def test_response_rejects_quantile_crossing() -> None:
    response = valid_response().model_dump(mode="python")
    response["quantiles"]["0.8"][0][0] = 100.0
    response["quantiles"]["0.9"][0][0] = 99.0
    with pytest.raises(ValidationError, match="quantile crossing"):
        Tirex2Response.model_validate(response)


def test_response_rejects_cuda_to_cpu_fallback() -> None:
    response = valid_response().model_dump(mode="python")
    response["runtime_evidence"]["requested_device"] = "cuda"
    response["runtime_evidence"]["effective_device"] = "cpu"
    response["runtime_evidence"]["cpu_fallback"] = True
    with pytest.raises(ValidationError, match="silently fall back"):
        Tirex2Response.model_validate(response)


def test_covariate_matrix_rejects_nonfinite() -> None:
    with pytest.raises(ValidationError, match="finite"):
        CovariateBlock(
            names=["x"],
            values=[[float("nan")]],
            known_at_prediction_time=True,
        )


def test_geometry_rejects_impossible_increasing_capacity() -> None:
    with pytest.raises(ValidationError, match="capacity"):
        GameGeometry(
            game_id="invalid",
            position_count=5,
            candidate_min=1,
            candidate_max=3,
            strictly_increasing=True,
        )

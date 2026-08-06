from __future__ import annotations

import math
from collections.abc import Iterable

from .contract import (
    CandidateProbability,
    CandidateScore,
    Device,
    GPUEvidence,
    QuantileForecast,
    TabPFNTSResponseV2,
)
from .geometry import GameGeometry


def rank_candidate_scores(
    scores: Iterable[CandidateScore], geometry: GameGeometry
) -> tuple[list[int], list[int]]:
    """Return score-ranked candidates and their sorted position representation."""

    if not geometry.strictly_increasing:
        raise ValueError(
            "candidate-score ranking requires a strictly increasing unique-selection game"
        )
    score_list = list(scores)
    expected = set(range(geometry.candidate_min, geometry.candidate_max + 1))
    actual = {item.candidate for item in score_list}
    if actual != expected or len(score_list) != len(expected):
        raise ValueError("candidate scores must cover the candidate universe exactly once")

    ranked = [
        item.candidate
        for item in sorted(
            score_list,
            key=lambda item: (-item.raw_candidate_regression_score, item.candidate),
        )[: geometry.selection_count]
    ]
    return ranked, sorted(ranked)


def validate_calibrated_probabilities(
    probabilities: Iterable[CandidateProbability],
    geometry: GameGeometry,
    *,
    sum_tolerance: float = 1e-3,
) -> None:
    values = list(probabilities)
    expected = set(range(geometry.candidate_min, geometry.candidate_max + 1))
    actual = {item.candidate for item in values}
    if actual != expected or len(values) != len(expected):
        raise ValueError("calibrated probabilities must cover each candidate exactly once")
    total = sum(item.calibrated_probability for item in values)
    if not math.isclose(total, geometry.selection_count, abs_tol=sum_tolerance):
        raise ValueError("calibrated probabilities must sum approximately to selection_count")


def require_strict_gpu_success(evidence: GPUEvidence) -> None:
    if evidence.requested_device is not Device.CUDA:
        return
    if evidence.effective_device is not Device.CUDA or evidence.cpu_fallback:
        raise ValueError("FAILED_CPU_FALLBACK")
    device_values = (
        evidence.model_parameter_device,
        evidence.training_table_device,
        evidence.test_table_device,
        evidence.prediction_tensor_device,
    )
    if any(value is None or not value.startswith("cuda") for value in device_values):
        raise ValueError("GPU_PARTIAL: missing measured CUDA device evidence")
    if evidence.gpu_uuid is None:
        raise ValueError("GPU_PARTIAL: gpu_uuid is required")


def _point_mapping(response: TabPFNTSResponseV2) -> dict[tuple[str, int], float]:
    return {
        (item.series_id, item.horizon_step): item.value
        for item in response.point_forecast
    }


def _quantile_mapping(
    quantiles: list[QuantileForecast],
) -> dict[tuple[float, str, int], float]:
    return {
        (quantile.level, item.series_id, item.horizon_step): item.value
        for quantile in quantiles
        for item in quantile.values
    }


def validate_local_batch_parity(
    local_response: TabPFNTSResponseV2,
    batch_response: TabPFNTSResponseV2,
    *,
    absolute_tolerance: float = 0.0,
) -> None:
    if local_response.series_identity != batch_response.series_identity:
        raise ValueError("series identity differs between local and batch responses")
    if local_response.prediction_index != batch_response.prediction_index:
        raise ValueError("horizon identity differs between local and batch responses")

    local_points = _point_mapping(local_response)
    batch_points = _point_mapping(batch_response)
    if set(local_points) != set(batch_points):
        raise ValueError("point output shapes differ between local and batch responses")
    for key in local_points:
        if not math.isclose(
            local_points[key],
            batch_points[key],
            rel_tol=0.0,
            abs_tol=absolute_tolerance,
        ):
            raise ValueError(f"point parity mismatch for {key}")

    local_quantiles = _quantile_mapping(local_response.quantiles)
    batch_quantiles = _quantile_mapping(batch_response.quantiles)
    if set(local_quantiles) != set(batch_quantiles):
        raise ValueError("quantile output shapes differ between local and batch responses")
    for key in local_quantiles:
        if not math.isclose(
            local_quantiles[key],
            batch_quantiles[key],
            rel_tol=0.0,
            abs_tol=absolute_tolerance,
        ):
            raise ValueError(f"quantile parity mismatch for {key}")

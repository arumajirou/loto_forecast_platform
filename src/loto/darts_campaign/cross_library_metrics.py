from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Literal

import numpy as np

from .cross_library_contract import FairnessContract, ProviderExecution
from .cross_library_models import (
    AggregateMetric,
    CrossLibraryCertificationError,
    ExecutionEvidence,
    ForecastRecord,
    MetricVector,
    ProviderMetricResult,
)


def _metric_for_records(
    records: Sequence[ForecastRecord],
    fairness: FairnessContract,
) -> MetricVector:
    if not records:
        raise CrossLibraryCertificationError("no records available for metric calculation")
    actual = np.asarray([record.actual for record in records], dtype=float)
    predicted = np.asarray([record.predicted for record in records], dtype=float)
    absolute = np.abs(actual - predicted)
    squared = np.square(actual - predicted)
    position_hits: dict[str, float] = {}
    for position in fairness.positions:
        mask = np.asarray([record.position == position for record in records], dtype=bool)
        if not mask.any():
            raise CrossLibraryCertificationError(f"missing position records: {position}")
        position_hits[position] = float((absolute[mask] <= 1.0).mean())
    grouped: dict[tuple[int, int, int], dict[str, bool]] = defaultdict(dict)
    for record, error in zip(records, absolute, strict=True):
        key = (record.seed, record.fold_id, record.target_index)
        if record.position in grouped[key]:
            raise CrossLibraryCertificationError("duplicate position within a forecast target")
        grouped[key][record.position] = bool(error <= 1.0)
    all_position_hits: list[bool] = []
    expected_positions = set(fairness.positions)
    for position_hits_by_target in grouped.values():
        if set(position_hits_by_target) != expected_positions:
            raise CrossLibraryCertificationError("forecast target lacks complete position coverage")
        all_position_hits.append(all(position_hits_by_target.values()))
    return MetricVector(
        hit_at_plus_minus_1=float((absolute <= 1.0).mean()),
        all_position_hit_at_plus_minus_1=float(np.mean(all_position_hits)),
        mae=float(absolute.mean()),
        mse=float(squared.mean()),
        rmse=float(np.sqrt(squared.mean())),
        position_hit_at_plus_minus_1=position_hits,
    )


def _aggregate_seed_metrics(seed_metrics: Mapping[int, MetricVector]) -> AggregateMetric:
    if len(seed_metrics) < 2:
        raise CrossLibraryCertificationError("multi-seed aggregation requires at least two seeds")
    positions = tuple(next(iter(seed_metrics.values())).position_hit_at_plus_minus_1)

    def vector(kind: Literal["mean", "variance", "worst"]) -> MetricVector:
        values = list(seed_metrics.values())

        def scalar(name: str, *, higher_is_better: bool) -> float:
            array = np.asarray([getattr(item, name) for item in values], dtype=float)
            if kind == "mean":
                return float(array.mean())
            if kind == "variance":
                return float(array.var(ddof=0))
            return float(array.min() if higher_is_better else array.max())

        position_values: dict[str, float] = {}
        for position in positions:
            array = np.asarray(
                [item.position_hit_at_plus_minus_1[position] for item in values],
                dtype=float,
            )
            if kind == "mean":
                position_values[position] = float(array.mean())
            elif kind == "variance":
                position_values[position] = float(array.var(ddof=0))
            else:
                position_values[position] = float(array.min())
        return MetricVector(
            hit_at_plus_minus_1=scalar(
                "hit_at_plus_minus_1",
                higher_is_better=True,
            ),
            all_position_hit_at_plus_minus_1=scalar(
                "all_position_hit_at_plus_minus_1",
                higher_is_better=True,
            ),
            mae=scalar("mae", higher_is_better=False),
            mse=scalar("mse", higher_is_better=False),
            rmse=scalar("rmse", higher_is_better=False),
            position_hit_at_plus_minus_1=position_values,
        )

    return AggregateMetric(
        mean=vector("mean"),
        variance=vector("variance"),
        worst=vector("worst"),
        seed_metrics=dict(seed_metrics),
    )


def evaluate_execution(
    provider: ProviderExecution,
    evidence: ExecutionEvidence,
    fairness: FairnessContract,
) -> ProviderMetricResult:
    if evidence.status != "SUCCESS":
        raise CrossLibraryCertificationError("failed execution cannot be formally evaluated")
    if evidence.provider_id != provider.provider_id:
        raise CrossLibraryCertificationError("provider ID mismatch")
    expected_fairness_hash = fairness.contract_sha256()
    if evidence.fairness_sha256 != expected_fairness_hash:
        raise CrossLibraryCertificationError("fairness contract hash mismatch")
    if evidence.data_sha256 != fairness.comparison_data_sha256:
        raise CrossLibraryCertificationError("comparison data hash mismatch")
    keys = [record.comparison_key() for record in evidence.records]
    if len(keys) != len(set(keys)):
        raise CrossLibraryCertificationError("duplicate forecast comparison keys")
    if any(record.provider_id != provider.provider_id for record in evidence.records):
        raise CrossLibraryCertificationError("record provider ID mismatch")
    expected_seed_set = set(fairness.seeds)
    observed_seed_set = {record.seed for record in evidence.records}
    if observed_seed_set != expected_seed_set:
        raise CrossLibraryCertificationError("seed coverage differs from fairness contract")
    if {record.fold_id for record in evidence.records} != set(fairness.fold_ids):
        raise CrossLibraryCertificationError("fold coverage differs from fairness contract")
    if any(record.position not in fairness.positions for record in evidence.records):
        raise CrossLibraryCertificationError("unexpected forecast position")
    seed_metrics: dict[int, MetricVector] = {}
    for seed in fairness.seeds:
        seed_records = [record for record in evidence.records if record.seed == seed]
        seed_metrics[seed] = _metric_for_records(seed_records, fairness)
    prediction_hash = evidence.prediction_sha256()
    assert prediction_hash is not None
    return ProviderMetricResult(
        provider_id=provider.provider_id,
        algorithm_key=provider.algorithm.canonical_key(),
        execution_key=provider.execution_key(),
        canonical_for_algorithm=provider.canonical_for_algorithm,
        metrics=_aggregate_seed_metrics(seed_metrics),
        prediction_sha256=prediction_hash,
        record_count=len(evidence.records),
    )


def certify_prediction_key_parity(evidence: Sequence[ExecutionEvidence]) -> int:
    successful = [item for item in evidence if item.status == "SUCCESS"]
    if not successful:
        raise CrossLibraryCertificationError("no successful provider executions")
    reference = {record.comparison_key() for record in successful[0].records}
    for item in successful[1:]:
        current = {record.comparison_key() for record in item.records}
        if current != reference:
            raise CrossLibraryCertificationError(
                f"prediction key coverage mismatch for provider {item.provider_id}"
            )
    return len(reference)

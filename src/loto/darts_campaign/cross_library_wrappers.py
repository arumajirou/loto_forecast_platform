from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from .cross_library_contract import CrossLibraryCampaignConfig
from .cross_library_models import (
    CrossLibraryCertificationError,
    ExecutionEvidence,
    ProviderMetricResult,
    WrapperComparison,
)


def compare_wrapper_variants(
    config: CrossLibraryCampaignConfig,
    evidence_by_provider: Mapping[str, ExecutionEvidence],
    metrics_by_provider: Mapping[str, ProviderMetricResult],
) -> tuple[WrapperComparison, ...]:
    comparisons: list[WrapperComparison] = []
    for algorithm_key, providers in config.algorithm_groups().items():
        successful = [
            provider
            for provider in providers
            if evidence_by_provider[provider.provider_id].status == "SUCCESS"
        ]
        if len(successful) < 2:
            continue
        canonical = [provider for provider in successful if provider.canonical_for_algorithm]
        if len(canonical) != 1:
            raise CrossLibraryCertificationError(
                "successful algorithm variants require one canonical provider"
            )
        canonical_provider = canonical[0]
        canonical_evidence = evidence_by_provider[canonical_provider.provider_id]
        canonical_records = {
            record.comparison_key(): record.predicted
            for record in canonical_evidence.records
        }
        canonical_metrics = metrics_by_provider[canonical_provider.provider_id].metrics.mean
        for variant in successful:
            if variant.provider_id == canonical_provider.provider_id:
                continue
            variant_evidence = evidence_by_provider[variant.provider_id]
            variant_records = {
                record.comparison_key(): record.predicted
                for record in variant_evidence.records
            }
            if set(variant_records) != set(canonical_records):
                raise CrossLibraryCertificationError("wrapper comparison key mismatch")
            deltas = np.asarray(
                [
                    abs(canonical_records[key] - variant_records[key])
                    for key in sorted(canonical_records)
                ],
                dtype=float,
            )
            parity = bool(
                np.allclose(
                    np.asarray(
                        [canonical_records[key] for key in sorted(canonical_records)],
                        dtype=float,
                    ),
                    np.asarray(
                        [variant_records[key] for key in sorted(variant_records)],
                        dtype=float,
                    ),
                    atol=config.wrapper_prediction_atol,
                    rtol=config.wrapper_prediction_rtol,
                )
            )
            if config.require_wrapper_prediction_parity and not parity:
                raise CrossLibraryCertificationError(
                    f"wrapper prediction parity failed: {variant.provider_id}"
                )
            variant_metrics = metrics_by_provider[variant.provider_id].metrics.mean
            comparisons.append(
                WrapperComparison(
                    algorithm_key=algorithm_key,
                    canonical_provider_id=canonical_provider.provider_id,
                    variant_provider_id=variant.provider_id,
                    comparison_key_count=len(deltas),
                    max_abs_prediction_delta=float(deltas.max()),
                    mean_abs_prediction_delta=float(deltas.mean()),
                    hit_at_plus_minus_1_delta=(
                        variant_metrics.hit_at_plus_minus_1
                        - canonical_metrics.hit_at_plus_minus_1
                    ),
                    all_position_hit_delta=(
                        variant_metrics.all_position_hit_at_plus_minus_1
                        - canonical_metrics.all_position_hit_at_plus_minus_1
                    ),
                    mae_delta=variant_metrics.mae - canonical_metrics.mae,
                    prediction_parity_required=config.require_wrapper_prediction_parity,
                    prediction_parity_passed=parity,
                )
            )
    return tuple(comparisons)

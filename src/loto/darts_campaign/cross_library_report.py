from __future__ import annotations

from collections.abc import Sequence

from .cross_library_contract import (
    REQUIRED_BASELINES,
    CrossLibraryCampaignConfig,
    CrossLibraryContractError,
    canonical_sha256,
)
from .cross_library_metrics import (
    certify_prediction_key_parity,
    evaluate_execution,
)
from .cross_library_models import (
    BaselineResult,
    ChampionDecision,
    CrossLibraryCertificationError,
    CrossLibraryReport,
    ExecutionEvidence,
    ProviderMetricResult,
)
from .cross_library_wrappers import compare_wrapper_variants


def select_champion(
    provider_results: Sequence[ProviderMetricResult],
    baselines: Sequence[BaselineResult],
) -> ChampionDecision:
    baseline_ids = {baseline.baseline_id for baseline in baselines}
    if baseline_ids != set(REQUIRED_BASELINES):
        raise CrossLibraryContractError("champion gate requires every baseline family")
    canonical = [result for result in provider_results if result.canonical_for_algorithm]
    if not canonical:
        return ChampionDecision(
            status="NO_CHAMPION",
            reason="no successful canonical algorithm execution",
        )
    baseline_mean_hit = max(baseline.metrics.mean.hit_at_plus_minus_1 for baseline in baselines)
    baseline_worst_hit = max(baseline.metrics.worst.hit_at_plus_minus_1 for baseline in baselines)
    eligible = [
        result
        for result in canonical
        if result.metrics.mean.hit_at_plus_minus_1 > baseline_mean_hit
        and result.metrics.worst.hit_at_plus_minus_1 >= baseline_worst_hit
    ]
    if not eligible:
        return ChampionDecision(
            status="NO_CHAMPION",
            reason=(
                "no canonical algorithm improves baseline mean Hit@±1 without worst-seed regression"
            ),
        )
    eligible.sort(
        key=lambda result: (
            result.metrics.mean.hit_at_plus_minus_1,
            result.metrics.worst.hit_at_plus_minus_1,
            result.metrics.mean.all_position_hit_at_plus_minus_1,
            -result.metrics.mean.mae,
        ),
        reverse=True,
    )
    winner = eligible[0]
    return ChampionDecision(
        status="CHAMPION",
        provider_id=winner.provider_id,
        algorithm_key=winner.algorithm_key,
        reason="best deduplicated canonical execution passed the baseline gate",
    )


def build_cross_library_report(
    config: CrossLibraryCampaignConfig,
    evidence: Sequence[ExecutionEvidence],
    baselines: Sequence[BaselineResult],
) -> CrossLibraryReport:
    provider_map = config.provider_map()
    evidence_by_provider = {item.provider_id: item for item in evidence}
    if set(evidence_by_provider) != set(provider_map):
        missing = sorted(set(provider_map) - set(evidence_by_provider))
        extra = sorted(set(evidence_by_provider) - set(provider_map))
        raise CrossLibraryCertificationError(
            f"provider evidence mismatch: missing={missing}, extra={extra}"
        )
    certify_prediction_key_parity(evidence)
    provider_results: list[ProviderMetricResult] = []
    failed_provider_ids: list[str] = []
    for provider in config.providers:
        current = evidence_by_provider[provider.provider_id]
        if current.status == "FAILED":
            failed_provider_ids.append(provider.provider_id)
            continue
        provider_results.append(evaluate_execution(provider, current, config.fairness))
    metrics_by_provider = {result.provider_id: result for result in provider_results}
    wrapper_comparisons = compare_wrapper_variants(
        config,
        evidence_by_provider,
        metrics_by_provider,
    )
    canonical_algorithm_count = len(
        {result.algorithm_key for result in provider_results if result.canonical_for_algorithm}
    )
    champion = select_champion(provider_results, baselines)
    payload = {
        "fairness_sha256": config.fairness.contract_sha256(),
        "provider_results": [item.model_dump(mode="json") for item in provider_results],
        "failed_provider_ids": failed_provider_ids,
        "wrapper_comparisons": [item.model_dump(mode="json") for item in wrapper_comparisons],
        "canonical_algorithm_count": canonical_algorithm_count,
        "execution_count": len(evidence),
        "champion": champion.model_dump(mode="json"),
    }
    return CrossLibraryReport(
        fairness_sha256=config.fairness.contract_sha256(),
        provider_results=tuple(provider_results),
        failed_provider_ids=tuple(failed_provider_ids),
        wrapper_comparisons=wrapper_comparisons,
        canonical_algorithm_count=canonical_algorithm_count,
        execution_count=len(evidence),
        champion=champion,
        report_sha256=canonical_sha256(payload),
    )

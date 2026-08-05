from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from .cross_library_certification import ExecutionEvidence, ForecastRecord
from .cross_library_contract import CrossLibraryCampaignConfig, ProviderExecution


class CrossLibraryRuntime(Protocol):
    def execute(self, provider: ProviderExecution) -> Mapping[str, Any]:
        """Execute one provider and return auditable runtime evidence."""


def run_cross_library_matrix(
    config: CrossLibraryCampaignConfig,
    runtime: CrossLibraryRuntime,
) -> tuple[ExecutionEvidence, ...]:
    results: list[ExecutionEvidence] = []
    fairness_hash = config.fairness.contract_sha256()
    for provider in config.providers:
        try:
            payload = dict(runtime.execute(provider))
            records = tuple(
                record
                if isinstance(record, ForecastRecord)
                else ForecastRecord.model_validate(record)
                for record in payload.pop("records")
            )
            results.append(
                ExecutionEvidence(
                    provider_id=provider.provider_id,
                    status="SUCCESS",
                    fairness_sha256=fairness_hash,
                    data_sha256=config.fairness.comparison_data_sha256,
                    requested_device=provider.requested_device,
                    records=records,
                    **payload,
                )
            )
        except Exception as error:
            results.append(
                ExecutionEvidence(
                    provider_id=provider.provider_id,
                    status="FAILED",
                    fairness_sha256=fairness_hash,
                    data_sha256=config.fairness.comparison_data_sha256,
                    config_sha256=provider.algorithm.model_config_sha256,
                    code_sha256=config.fairness.code_contract_sha256,
                    git_commit="unknown-failure",
                    package_versions={},
                    requested_device=provider.requested_device,
                    effective_device="not_applicable",
                    failure_class=type(error).__name__,
                    failure_message=str(error),
                )
            )
    return tuple(results)

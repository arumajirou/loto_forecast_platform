from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from loto.darts_campaign.cross_library import (
    PROVIDER_TRACKS,
    CrossLibraryCampaignConfig,
    CrossLibraryCertificationError,
    ExecutionEvidence,
    FairnessContract,
    ProviderExecution,
    TemporalBoundaries,
    build_cross_library_report,
    canonical_sha256,
    certify_prediction_key_parity,
    evaluate_execution,
    run_cross_library_matrix,
)
from .cross_library_fixtures import (
    HASH_A,
    HASH_B,
    HASH_E,
    _algorithm,
    _baselines,
    _config,
    _evidence,
    _fairness,
    _providers,
    _records,
)


def test_matrix_retains_each_provider_failure_without_stopping() -> None:
    config = _config()

    @dataclass
    class Runtime:
        def execute(self, provider: ProviderExecution) -> dict[str, object]:
            if provider.provider_id == "mlforecast-linear":
                raise RuntimeError("provider unavailable")
            gpu = {}
            effective = "cpu"
            if provider.requested_device == "gpu":
                effective = "gpu"
                gpu = {
                    "process_pid": 100,
                    "gpu_pid": 100,
                    "vram_before_bytes": 1,
                    "vram_peak_bytes": 2,
                    "vram_after_bytes": 1,
                }
            return {
                "config_sha256": provider.algorithm.model_config_sha256,
                "code_sha256": config.fairness.code_contract_sha256,
                "git_commit": "abcdef123",
                "package_versions": {},
                "effective_device": effective,
                "gpu_evidence": gpu,
                "records": _records(provider.provider_id),
            }

    results = run_cross_library_matrix(config, Runtime())
    assert len(results) == 8
    failed = [item for item in results if item.status == "FAILED"]
    assert len(failed) == 1
    assert failed[0].provider_id == "mlforecast-linear"
    assert failed[0].failure_class == "RuntimeError"


def test_report_retains_failed_provider_and_hash_is_tamper_sensitive() -> None:
    config = _config()
    evidence = []
    for provider in config.providers:
        if provider.provider_id == "darts-native-arima":
            evidence.append(
                ExecutionEvidence(
                    provider_id=provider.provider_id,
                    status="FAILED",
                    fairness_sha256=config.fairness.contract_sha256(),
                    data_sha256=config.fairness.comparison_data_sha256,
                    config_sha256=provider.algorithm.model_config_sha256,
                    code_sha256=config.fairness.code_contract_sha256,
                    git_commit="abcdef123",
                    package_versions={},
                    requested_device="cpu",
                    effective_device="not_applicable",
                    failure_class="ImportError",
                    failure_message="missing optional dependency",
                )
            )
        else:
            evidence.append(_evidence(provider, config.fairness))
    report = build_cross_library_report(config, tuple(evidence), _baselines())
    assert report.failed_provider_ids == ("darts-native-arima",)
    assert report.execution_count == 8
    assert report.report_sha256 == report.report_sha256
    payload = report.model_dump(mode="json")
    payload["execution_count"] = 9
    assert report.report_sha256 != canonical_sha256(payload)

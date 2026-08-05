from __future__ import annotations

from loto.adapters.gluonts.p6_contract import DistributionMode
from loto.adapters.gluonts.p6_registry import (
    EXPECTED_MODELS,
    model_specs,
    registry_payload,
    registry_sha256,
)


def test_registry_contains_exactly_nine_expected_models() -> None:
    specs = model_specs()
    assert tuple(spec.model_class for spec in specs) == EXPECTED_MODELS
    assert len({spec.model_class for spec in specs}) == 9


def test_registry_distribution_contracts_are_explicit() -> None:
    by_name = {spec.model_class: spec for spec in model_specs()}
    student_t = {
        name
        for name, spec in by_name.items()
        if spec.distribution_mode is DistributionMode.STUDENT_T
    }
    assert student_t == {
        "DeepAREstimator",
        "TemporalFusionTransformerEstimator",
    }
    intrinsic = {
        name
        for name, spec in by_name.items()
        if spec.distribution_mode is DistributionMode.INTRINSIC
    }
    assert intrinsic == {
        "DeepNPTSEstimator",
        "TiDEEstimator",
        "SimpleFeedForwardEstimator",
        "WaveNetEstimator",
        "DLinearEstimator",
        "PatchTSTEstimator",
        "LagTSTEstimator",
    }


def test_registry_resource_limits_are_uniform_and_bounded() -> None:
    for spec in model_specs():
        assert spec.resource_limits.max_epochs == 1
        assert spec.resource_limits.max_batches_per_epoch == 1
        assert spec.resource_limits.max_batch_size == 4
        assert spec.resource_limits.max_parallel_samples == 4
        assert spec.resource_limits.threads_per_job == 1
        assert spec.resource_limits.device == "cpu"


def test_registry_hash_matches_payload() -> None:
    payload = registry_payload()
    assert payload["registry_sha256"] == registry_sha256()
    assert payload["constructor_change_between_tags"] is False

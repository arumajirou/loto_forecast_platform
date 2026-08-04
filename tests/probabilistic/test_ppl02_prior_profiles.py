from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml
from pydantic import ValidationError

from loto.game.geometry import geometry_for
from loto.probabilistic.catalog import (
    catalog_counts,
    get_probabilistic_model_spec,
    list_probabilistic_model_specs,
)
from loto.probabilistic.compatibility import decide_compatibility
from loto.probabilistic.config import execution_fingerprint, load_run_config
from loto.probabilistic.contracts import ProbabilisticRunConfig
from loto.probabilistic.planner import build_plan
from loto.probabilistic.priors import (
    PriorProfileSpec,
    decide_prior_profile_compatibility,
    get_prior_profile,
    list_prior_profiles,
    load_prior_profile_registry,
    sample_r2d2_prior,
    sample_spike_slab_prior,
    spike_slab_toy_inclusion_posterior,
    verify_prior_profile_toy,
)
from loto.probabilistic.statuses import CompatibilityReason


def test_registry_preserves_legacy_profiles_and_adds_batch9_contracts() -> None:
    profiles = {profile.profile_id: profile for profile in list_prior_profiles()}
    assert set(profiles) == {
        "symmetric-dirichlet-v1",
        "weak-dirichlet-v1",
        "strong-smoothing-dirichlet-v1",
        "r2d2",
        "spike_slab",
    }
    assert profiles["r2d2"].model_dump(mode="json") == {
        "profile_id": "r2d2",
        "family": "r2d2",
        "supported_backends": ["pymc", "numpyro"],
        "requires_exogenous": True,
        "execution_status": "CONTRACT_ONLY",
        "notes": "PPL-02 Batch 9 contract and toy verification; model adapters are P1.",
        "concentration": None,
        "positive_mass_required": None,
        "r2_alpha": 1.0,
        "r2_beta": 4.0,
        "allocation": "dirichlet",
        "inclusion_probability": None,
        "slab_scale": None,
    }
    assert profiles["spike_slab"].inclusion_probability == 0.1
    assert profiles["spike_slab"].slab_scale == 1.0
    assert profiles["weak-dirichlet-v1"].execution_status == "CONTRACT_ONLY"


def test_profile_schema_is_fail_closed() -> None:
    with pytest.raises(ValidationError, match="r2d2 profiles require"):
        PriorProfileSpec.model_validate(
            {
                "profile_id": "bad-r2d2",
                "family": "r2d2",
                "r2_alpha": 1.0,
                "supported_backends": ["pymc"],
            }
        )
    with pytest.raises(ValidationError, match="incompatible fields"):
        PriorProfileSpec.model_validate(
            {
                "profile_id": "bad-spike-slab",
                "family": "spike_slab",
                "inclusion_probability": 0.1,
                "slab_scale": 1.0,
                "r2_alpha": 1.0,
            }
        )


def test_registry_rejects_duplicate_profile_ids(tmp_path: Path) -> None:
    path = tmp_path / "profiles.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "2.0.0",
                "profiles": [
                    {
                        "profile_id": "r2d2",
                        "family": "r2d2",
                        "r2_alpha": 1.0,
                        "r2_beta": 4.0,
                        "allocation": "dirichlet",
                    },
                    {
                        "profile_id": "r2d2",
                        "family": "r2d2",
                        "r2_alpha": 2.0,
                        "r2_beta": 3.0,
                        "allocation": "dirichlet",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_prior_profile_registry(path)


def test_run_config_round_trip_and_unknown_profile_fail_closed(tmp_path: Path) -> None:
    config = ProbabilisticRunConfig(prior_profile="r2d2")
    restored = ProbabilisticRunConfig.model_validate(config.model_dump(mode="json"))
    assert restored == config
    with pytest.raises(ValidationError, match="must not be blank"):
        ProbabilisticRunConfig(prior_profile="  ")

    source = tmp_path / "unknown.yaml"
    source.write_text("prior_profile: missing-profile\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown prior profile"):
        load_run_config(source)


def test_r2d2_prior_draws_are_deterministic_and_preserve_variance_allocation() -> None:
    profile = get_prior_profile("r2d2")
    first = sample_r2d2_prior(profile, feature_count=7, draws=4096, seed=42)
    second = sample_r2d2_prior(profile, feature_count=7, draws=4096, seed=42)
    assert np.array_equal(first.r2, second.r2)
    assert np.array_equal(first.allocation, second.allocation)
    assert np.array_equal(first.coefficients, second.coefficients)
    assert first.allocation.shape == (4096, 7)
    assert np.allclose(first.allocation.sum(axis=1), 1.0)
    total_variance = first.r2 / (1.0 - first.r2)
    assert np.allclose(first.local_variance.sum(axis=1), total_variance)
    assert np.isfinite(first.coefficients).all()
    assert abs(float(first.r2.mean()) - 0.2) < 0.03
    report = verify_prior_profile_toy(profile, draws=4096, feature_count=7, seed=42)
    assert report.status == "PASS"
    assert all(report.checks.values())


def test_spike_slab_prior_has_explicit_inclusion_and_exact_toy_posterior() -> None:
    profile = get_prior_profile("spike_slab")
    samples = sample_spike_slab_prior(profile, feature_count=9, draws=8192, seed=7)
    assert samples.included.shape == (8192, 9)
    assert np.count_nonzero(samples.coefficients[~samples.included]) == 0
    assert abs(float(samples.included.mean()) - 0.1) < 0.02

    posterior = spike_slab_toy_inclusion_posterior(
        np.asarray([0.0, 1.0, 2.0, 5.0]),
        observation_scale=1.0,
        profile=profile,
    )
    assert np.isfinite(posterior).all()
    assert np.all((posterior >= 0.0) & (posterior <= 1.0))
    assert np.all(np.diff(posterior) > 0.0)
    assert posterior[-1] > 0.9
    report = verify_prior_profile_toy(profile, draws=8192, feature_count=9, seed=7)
    assert report.status == "PASS"
    assert all(report.checks.values())


def test_prior_compatibility_gate_requires_supported_exogenous_target() -> None:
    r2d2 = get_prior_profile("r2d2")
    exogenous = get_probabilistic_model_spec("pp-multinomial-logit-normal")
    non_exogenous = get_probabilistic_model_spec("pp-uniform-dirichlet")

    mismatch = decide_prior_profile_compatibility(
        r2d2,
        model_spec=exogenous,
        backend="builtin",
        exogenous_features_available=True,
        exogenous_feature_count=5,
    )
    assert not mismatch.allowed
    assert mismatch.reason_code == "PRIOR_PROFILE_BACKEND_MISMATCH"

    wrong_model = decide_prior_profile_compatibility(
        r2d2,
        model_spec=non_exogenous,
        backend="pymc",
        exogenous_features_available=True,
        exogenous_feature_count=5,
    )
    assert not wrong_model.allowed
    assert wrong_model.reason_code == "PRIOR_PROFILE_EXOGENOUS_MODEL_REQUIRED"

    missing_features = decide_prior_profile_compatibility(
        r2d2,
        model_spec=exogenous,
        backend="pymc",
        exogenous_features_available=False,
        exogenous_feature_count=0,
    )
    assert not missing_features.allowed
    assert missing_features.reason_code == "PRIOR_PROFILE_FEATURES_REQUIRED"

    contract_only = decide_prior_profile_compatibility(
        r2d2,
        model_spec=exogenous,
        backend="pymc",
        exogenous_features_available=True,
        exogenous_feature_count=5,
    )
    assert contract_only.allowed
    assert not contract_only.execution_ready
    assert contract_only.reason_code == "PRIOR_PROFILE_CONTRACT_ONLY"
    assert contract_only.model_id == exogenous.model_id


def test_integrated_compatibility_and_plan_block_contract_only_without_fallback() -> None:
    spec = get_probabilistic_model_spec("pp-multinomial-logit-normal")
    decision = decide_compatibility(
        spec,
        geometry=geometry_for("numbers3"),
        backend="pymc",
        prior_profile_id="r2d2",
        exogenous_features_available=True,
        exogenous_feature_count=4,
    )
    assert not decision.allowed
    assert decision.reason_code == CompatibilityReason.PRIOR_PROFILE_CONTRACT_ONLY
    assert "application_adapter_not_implemented=true" in decision.details

    config = ProbabilisticRunConfig(
        models=[spec.model_id],
        games=["numbers3"],
        backends=["pymc"],
        prior_profile="r2d2",
    )
    plan = build_plan(config)
    assert len(plan) == 1
    assert not plan[0].allowed
    assert plan[0].prior_profile_id == "r2d2"
    assert plan[0].reason_code == "PRIOR_PROFILE_CONTRACT_ONLY"


def test_prior_profile_changes_fingerprint_without_model_id_explosion() -> None:
    spec = get_probabilistic_model_spec("pp-multinomial-logit-normal")
    base = execution_fingerprint(
        protocol_hash="protocol",
        model_spec=spec,
        run_config=ProbabilisticRunConfig(),
        backend="builtin",
    )
    profiled = execution_fingerprint(
        protocol_hash="protocol",
        model_spec=spec,
        run_config=ProbabilisticRunConfig(prior_profile="r2d2"),
        backend="pymc",
    )
    assert base["prior_spec_hash"] != profiled["prior_spec_hash"]
    assert base["execution_fingerprint"] != profiled["execution_fingerprint"]

    model_ids = {model.model_id for model in list_probabilistic_model_specs()}
    assert "r2d2" not in model_ids
    assert "spike_slab" not in model_ids
    assert len(model_ids) == 76
    assert catalog_counts()["probabilistic_models"] == 76

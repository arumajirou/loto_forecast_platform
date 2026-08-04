from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PriorProfileSpec(BaseModel):
    """Validated prior-profile contract.

    PPL-02 Batch 9 deliberately separates a structural model ID from its prior
    configuration. R2-D2 and spike-and-slab therefore remain profiles and do
    not create duplicate catalog entries.
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1)
    family: Literal["dirichlet", "r2d2", "spike_slab"]
    supported_backends: tuple[str, ...] = ()
    requires_exogenous: bool = False
    execution_status: Literal["IMPLEMENTED", "CONTRACT_ONLY"] = "CONTRACT_ONLY"
    notes: str = ""

    concentration: float | None = Field(default=None, gt=0.0)
    positive_mass_required: bool | None = None

    r2_alpha: float | None = Field(default=None, gt=0.0)
    r2_beta: float | None = Field(default=None, gt=0.0)
    allocation: Literal["dirichlet"] | None = None

    inclusion_probability: float | None = Field(default=None, gt=0.0, lt=1.0)
    slab_scale: float | None = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def validate_family_fields(self) -> PriorProfileSpec:
        if len(self.supported_backends) != len(set(self.supported_backends)):
            raise ValueError("supported_backends must not contain duplicates")
        if self.family == "dirichlet":
            if self.concentration is None or self.positive_mass_required is None:
                raise ValueError(
                    "dirichlet profiles require concentration and positive_mass_required"
                )
            if any(
                value is not None
                for value in (
                    self.r2_alpha,
                    self.r2_beta,
                    self.allocation,
                    self.inclusion_probability,
                    self.slab_scale,
                )
            ):
                raise ValueError("dirichlet profiles contain incompatible fields")
        elif self.family == "r2d2":
            if self.r2_alpha is None or self.r2_beta is None or self.allocation is None:
                raise ValueError("r2d2 profiles require r2_alpha, r2_beta, and allocation")
            if any(
                value is not None
                for value in (
                    self.concentration,
                    self.positive_mass_required,
                    self.inclusion_probability,
                    self.slab_scale,
                )
            ):
                raise ValueError("r2d2 profiles contain incompatible fields")
        else:
            if self.inclusion_probability is None or self.slab_scale is None:
                raise ValueError("spike_slab profiles require inclusion_probability and slab_scale")
            if any(
                value is not None
                for value in (
                    self.concentration,
                    self.positive_mass_required,
                    self.r2_alpha,
                    self.r2_beta,
                    self.allocation,
                )
            ):
                raise ValueError("spike_slab profiles contain incompatible fields")
        return self


@dataclass(frozen=True)
class PriorProfileRegistry:
    schema_version: str
    profiles: tuple[PriorProfileSpec, ...]
    source: str

    def get(self, profile_id: str) -> PriorProfileSpec:
        for profile in self.profiles:
            if profile.profile_id == profile_id:
                return profile
        raise KeyError(f"unknown prior profile: {profile_id}")


@dataclass(frozen=True)
class PriorProfileDecision:
    allowed: bool
    execution_ready: bool
    reason_code: str
    model_id: str
    prior_profile_id: str
    backend: str
    details: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class R2D2PriorDraws:
    r2: np.ndarray
    allocation: np.ndarray
    local_variance: np.ndarray
    coefficients: np.ndarray


@dataclass(frozen=True)
class SpikeSlabPriorDraws:
    included: np.ndarray
    slab_coefficients: np.ndarray
    coefficients: np.ndarray


@dataclass(frozen=True)
class PriorToyVerificationReport:
    profile_id: str
    family: str
    status: Literal["PASS", "FAIL"]
    checks: dict[str, bool]
    metrics: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _default_registry_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "prior_profiles.yaml"


def load_prior_profile_registry(path: str | Path | None = None) -> PriorProfileRegistry:
    source = Path(path) if path is not None else _default_registry_path()
    payload = yaml.safe_load(source.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("prior profile registry must be a YAML mapping")
    schema_version = str(payload.get("schema_version", "")).strip()
    rows = payload.get("profiles")
    if not schema_version:
        raise ValueError("prior profile registry requires schema_version")
    if not isinstance(rows, list):
        raise ValueError("prior profile registry requires a profiles list")
    profiles = tuple(PriorProfileSpec.model_validate(row) for row in rows)
    profile_ids = [profile.profile_id for profile in profiles]
    if len(profile_ids) != len(set(profile_ids)):
        raise ValueError("prior profile registry contains duplicate profile_id values")
    return PriorProfileRegistry(schema_version, profiles, str(source))


def list_prior_profiles(path: str | Path | None = None) -> tuple[PriorProfileSpec, ...]:
    return load_prior_profile_registry(path).profiles


def get_prior_profile(profile_id: str, path: str | Path | None = None) -> PriorProfileSpec:
    return load_prior_profile_registry(path).get(profile_id)


def decide_prior_profile_compatibility(
    profile: PriorProfileSpec,
    *,
    model_spec: Any,
    backend: str,
    exogenous_features_available: bool,
    exogenous_feature_count: int,
) -> PriorProfileDecision:
    model_id = str(model_spec.model_id)
    if backend not in profile.supported_backends:
        return PriorProfileDecision(
            False,
            False,
            "PRIOR_PROFILE_BACKEND_MISMATCH",
            model_id,
            profile.profile_id,
            backend,
            (f"supported_backends={','.join(profile.supported_backends)}",),
        )
    if profile.requires_exogenous and not bool(model_spec.supports_exogenous):
        return PriorProfileDecision(
            False,
            False,
            "PRIOR_PROFILE_EXOGENOUS_MODEL_REQUIRED",
            model_id,
            profile.profile_id,
            backend,
            ("model_supports_exogenous=false",),
        )
    if profile.requires_exogenous and (
        not exogenous_features_available or exogenous_feature_count < 1
    ):
        return PriorProfileDecision(
            False,
            False,
            "PRIOR_PROFILE_FEATURES_REQUIRED",
            model_id,
            profile.profile_id,
            backend,
            (
                f"exogenous_features_available={str(exogenous_features_available).lower()}",
                f"exogenous_feature_count={exogenous_feature_count}",
            ),
        )
    if profile.execution_status != "IMPLEMENTED":
        return PriorProfileDecision(
            True,
            False,
            "PRIOR_PROFILE_CONTRACT_ONLY",
            model_id,
            profile.profile_id,
            backend,
            (
                f"family={profile.family}",
                "model_id_unchanged=true",
                "application_adapter_not_implemented=true",
            ),
        )
    return PriorProfileDecision(
        True,
        True,
        "ALLOWED",
        model_id,
        profile.profile_id,
        backend,
        (f"family={profile.family}", "model_id_unchanged=true"),
    )


def sample_r2d2_prior(
    profile: PriorProfileSpec,
    *,
    feature_count: int,
    draws: int,
    seed: int,
) -> R2D2PriorDraws:
    if profile.family != "r2d2":
        raise ValueError("sample_r2d2_prior requires an r2d2 profile")
    if feature_count < 1 or draws < 1:
        raise ValueError("feature_count and draws must be positive")
    assert profile.r2_alpha is not None
    assert profile.r2_beta is not None
    rng = np.random.default_rng(seed)
    r2 = rng.beta(profile.r2_alpha, profile.r2_beta, size=draws)
    r2 = np.clip(r2, np.finfo(np.float64).eps, 1.0 - np.finfo(np.float64).eps)
    allocation = rng.dirichlet(np.ones(feature_count, dtype=np.float64), size=draws)
    total_variance = r2 / (1.0 - r2)
    local_variance = total_variance[:, None] * allocation
    coefficients = rng.normal(loc=0.0, scale=np.sqrt(local_variance))
    return R2D2PriorDraws(r2, allocation, local_variance, coefficients)


def sample_spike_slab_prior(
    profile: PriorProfileSpec,
    *,
    feature_count: int,
    draws: int,
    seed: int,
) -> SpikeSlabPriorDraws:
    if profile.family != "spike_slab":
        raise ValueError("sample_spike_slab_prior requires a spike_slab profile")
    if feature_count < 1 or draws < 1:
        raise ValueError("feature_count and draws must be positive")
    assert profile.inclusion_probability is not None
    assert profile.slab_scale is not None
    rng = np.random.default_rng(seed)
    included = rng.random((draws, feature_count)) < profile.inclusion_probability
    slab_coefficients = rng.normal(
        loc=0.0,
        scale=profile.slab_scale,
        size=(draws, feature_count),
    )
    coefficients = np.where(included, slab_coefficients, 0.0)
    return SpikeSlabPriorDraws(included, slab_coefficients, coefficients)


def spike_slab_toy_inclusion_posterior(
    observed_effects: np.ndarray,
    *,
    observation_scale: float,
    profile: PriorProfileSpec,
) -> np.ndarray:
    """Exact inclusion posterior for an orthogonal Gaussian normal-means toy model."""

    if profile.family != "spike_slab":
        raise ValueError("spike_slab_toy_inclusion_posterior requires a spike_slab profile")
    if observation_scale <= 0.0:
        raise ValueError("observation_scale must be positive")
    assert profile.inclusion_probability is not None
    assert profile.slab_scale is not None
    values = np.asarray(observed_effects, dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("observed_effects must be finite")
    null_variance = observation_scale**2
    slab_variance = null_variance + profile.slab_scale**2
    log_null = -0.5 * (np.log(2.0 * np.pi * null_variance) + values**2 / null_variance)
    log_slab = -0.5 * (np.log(2.0 * np.pi * slab_variance) + values**2 / slab_variance)
    log_prior_odds = np.log(profile.inclusion_probability) - np.log1p(
        -profile.inclusion_probability
    )
    log_odds = log_prior_odds + log_slab - log_null
    posterior = np.empty_like(log_odds)
    nonnegative = log_odds >= 0.0
    posterior[nonnegative] = 1.0 / (1.0 + np.exp(-log_odds[nonnegative]))
    exp_values = np.exp(log_odds[~nonnegative])
    posterior[~nonnegative] = exp_values / (1.0 + exp_values)
    return posterior


def verify_prior_profile_toy(
    profile: PriorProfileSpec,
    *,
    draws: int = 4096,
    feature_count: int = 8,
    seed: int = 42,
) -> PriorToyVerificationReport:
    if profile.family == "r2d2":
        samples = sample_r2d2_prior(
            profile,
            feature_count=feature_count,
            draws=draws,
            seed=seed,
        )
        assert profile.r2_alpha is not None
        assert profile.r2_beta is not None
        expected_r2 = profile.r2_alpha / (profile.r2_alpha + profile.r2_beta)
        total_variance = samples.r2 / (1.0 - samples.r2)
        checks = {
            "finite": bool(
                np.isfinite(samples.r2).all()
                and np.isfinite(samples.allocation).all()
                and np.isfinite(samples.local_variance).all()
                and np.isfinite(samples.coefficients).all()
            ),
            "allocation_simplex": bool(
                np.allclose(samples.allocation.sum(axis=1), 1.0, atol=1e-12)
            ),
            "variance_decomposition": bool(
                np.allclose(samples.local_variance.sum(axis=1), total_variance, atol=1e-12)
            ),
            "r2_mean_consistent": bool(abs(float(samples.r2.mean()) - expected_r2) <= 0.03),
        }
        metrics = {
            "empirical_r2_mean": float(samples.r2.mean()),
            "expected_r2_mean": float(expected_r2),
            "maximum_allocation_error": float(np.abs(samples.allocation.sum(axis=1) - 1.0).max()),
        }
    elif profile.family == "spike_slab":
        samples = sample_spike_slab_prior(
            profile,
            feature_count=feature_count,
            draws=draws,
            seed=seed,
        )
        assert profile.inclusion_probability is not None
        posterior = spike_slab_toy_inclusion_posterior(
            np.asarray([0.0, 1.0, 5.0]),
            observation_scale=1.0,
            profile=profile,
        )
        checks = {
            "finite": bool(
                np.isfinite(samples.slab_coefficients).all()
                and np.isfinite(samples.coefficients).all()
                and np.isfinite(posterior).all()
            ),
            "excluded_coefficients_zero": bool(
                np.count_nonzero(samples.coefficients[~samples.included]) == 0
            ),
            "inclusion_rate_consistent": bool(
                abs(float(samples.included.mean()) - profile.inclusion_probability) <= 0.03
            ),
            "posterior_is_explicit_probability": bool(
                np.all((posterior >= 0.0) & (posterior <= 1.0))
            ),
            "stronger_effect_increases_inclusion": bool(np.all(np.diff(posterior) > 0.0)),
        }
        metrics = {
            "empirical_inclusion_rate": float(samples.included.mean()),
            "configured_inclusion_probability": float(profile.inclusion_probability),
            "null_effect_posterior": float(posterior[0]),
            "strong_effect_posterior": float(posterior[-1]),
        }
    else:
        checks = {
            "positive_concentration": bool(profile.concentration and profile.concentration > 0.0),
            "positive_mass_required": bool(profile.positive_mass_required),
        }
        metrics = {"concentration": float(profile.concentration or 0.0)}
    return PriorToyVerificationReport(
        profile_id=profile.profile_id,
        family=profile.family,
        status="PASS" if all(checks.values()) else "FAIL",
        checks=checks,
        metrics=metrics,
    )

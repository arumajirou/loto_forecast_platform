from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


@dataclass(frozen=True)
class ProbabilisticModelSpec:
    schema_version: str
    model_id: str
    family: str
    role: Literal["control", "baseline", "candidate", "research", "meta"]
    likelihood: str
    latent_structure: str
    backends: tuple[str, ...]
    tasks: tuple[str, ...]
    priority: Literal["p0", "p1", "p2"]
    supports_exogenous: bool
    hierarchical: bool
    dynamic: bool
    experimental: bool
    notes: str = ""
    implementation_status: str = "IMPLEMENTED"
    reference_strategy: str = "generic"
    primary_backend: str = "builtin"
    primary_profile: str | None = None
    native_implementation_status: str = "IMPLEMENTED"
    native_graph_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InferenceProfileSpec:
    profile_id: str
    backend: str
    algorithm: str
    tier: str
    continuous_only: bool
    default: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompatibilityDecision:
    allowed: bool
    reason_code: str
    resolved_backend: str | None
    resolved_profile: str | None
    required_resource_class: str | None
    details: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PredictiveDistribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    game: str
    target_mode: str
    draw_id: str
    position: int | None = None
    candidate: int
    probability_mean: float = Field(ge=0.0, le=1.0)
    probability_sd: float = Field(ge=0.0)
    hdi_low: float = Field(ge=0.0, le=1.0)
    hdi_high: float = Field(ge=0.0, le=1.0)
    posterior_draw_count: int = Field(ge=1)
    protocol_hash: str
    execution_fingerprint: str

    @model_validator(mode="after")
    def validate_interval(self) -> PredictiveDistribution:
        if self.hdi_low > self.hdi_high:
            raise ValueError("hdi_low must not exceed hdi_high")
        return self


class DiagnosticReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["PASS", "WARN", "FAIL", "NOT_APPLICABLE"]
    backend: str
    inference_profile_id: str | None = None
    rhat_max: float | None = None
    ess_bulk_min: float | None = None
    ess_tail_min: float | None = None
    divergences: int | None = None
    max_treedepth_hits: int | None = None
    ebfmi_min: float | None = None
    elbo_finite: bool | None = None
    elbo_stable: bool | None = None
    posterior_finite: bool
    probability_simplex_valid: bool
    warnings: list[str] = Field(default_factory=list)
    failure_codes: list[str] = Field(default_factory=list)
    effective_sample_size: float | None = None
    prediction_entropy: float | None = None
    unique_point_predictions: int | None = None


class ProbabilisticRunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0.0"
    run_id: str | None = None
    profile: Literal["smoke", "standard", "full", "exhaustive"] = "smoke"
    games: list[str] = Field(default_factory=lambda: ["numbers3", "loto7"])
    inputs: dict[str, str] = Field(default_factory=dict)
    output: str = "runs/probabilistic"
    models: list[str] | Literal["all"] = "all"
    families: list[str] = Field(default_factory=list)
    backends: list[str] = Field(default_factory=lambda: ["builtin"])
    inference_profiles: list[str] = Field(default_factory=list)
    include_experimental: bool = True
    outer_workers: int = Field(default=8, ge=1, le=64)
    max_gpu_jobs: int = Field(default=1, ge=0, le=8)
    max_heavy_cpu_jobs: int = Field(default=2, ge=1, le=16)
    gpu_priority: bool = True
    gpu_backends: list[str] = Field(default_factory=lambda: ["numpyro", "pyro"])
    scheduling_policy: Literal["resource_aware", "legacy"] = "resource_aware"
    resume_policy: Literal["disabled", "skip_completed", "skip_pass"] = "disabled"
    seeds: list[int] = Field(default_factory=lambda: [42])
    folds: int = Field(default=1, ge=1, le=20)
    test_size: int = Field(default=5, ge=1, le=500)
    min_train_size: int = Field(default=60, ge=10)
    posterior_draws: int = Field(default=512, ge=32, le=100000)
    synthetic_rows: int = Field(default=240, ge=80, le=100000)
    rolling_window: int = Field(default=20, ge=2)
    discount_factor: float = Field(default=0.97, gt=0.0, le=1.0)
    prior_concentration: float = Field(default=1.0, gt=0.0)
    utility_lambda_mse: float = Field(default=0.02, ge=0.0)
    dry_run: bool = False
    save_posterior_draws: bool = False
    sealed_holdout: bool = True
    prospective_min_draws: int = Field(default=100, ge=1)
    backend_policy: Literal["requested", "primary_native", "all_declared"] = "requested"
    native_chains: int = Field(default=1, ge=1, le=8)
    native_warmup: int = Field(default=100, ge=0, le=100000)
    native_draws: int = Field(default=128, ge=8, le=100000)
    native_svi_steps: int = Field(default=500, ge=10, le=1000000)
    native_particles: int = Field(default=1, ge=1, le=128)
    native_max_train_rows: int = Field(default=500, ge=20, le=100000)
    native_target_accept: float = Field(default=0.9, ge=0.5, lt=1.0)
    native_progressbar: bool = False
    native_device: Literal["auto", "cpu", "cuda"] = "auto"
    native_inner_cores: int = Field(default=1, ge=1, le=8)
    native_compile_cache: str = "artifacts/probabilistic-native-cache"

    progress_write_interval_seconds: int = Field(default=5, ge=1, le=3600)
    eta_default_gpu_seconds: float = Field(default=180.0, gt=0.0)
    eta_default_heavy_cpu_seconds: float = Field(default=300.0, gt=0.0)
    eta_default_light_cpu_seconds: float = Field(default=15.0, gt=0.0)
    notify_every_completed: int = Field(default=5, ge=1, le=1000)
    notify_progress_seconds: int = Field(default=600, ge=30, le=86400)
    speech_enabled: bool = False
    speech_language: str = "ja"
    speech_engine: Literal["auto", "voicevox", "open_jtalk", "spd_say", "espeak"] = "auto"
    speech_min_interval_seconds: int = Field(default=60, ge=0, le=86400)
    voicevox_url: str = "http://127.0.0.1:50021"
    voicevox_speaker: int = Field(default=3, ge=0)
    voicevox_speed_scale: float = Field(default=1.15, gt=0.5, le=3.0)
    open_jtalk_dictionary: str | None = None
    open_jtalk_voice: str | None = None
    email_enabled: bool = False
    email_to: list[str] = Field(default_factory=list)
    email_from: str | None = None
    email_on_start: bool = True
    email_on_progress: bool = True
    email_on_failure: bool = True
    email_on_completion: bool = True
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username_env: str = "LOTO_SMTP_USERNAME"
    smtp_password_env: str = "LOTO_SMTP_APP_PASSWORD"
    notification_fail_open: bool = True

    @field_validator("games")
    @classmethod
    def games_not_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("games must not be empty")
        return value

    @model_validator(mode="after")
    def validate_parallelism(self) -> ProbabilisticRunConfig:
        if self.max_heavy_cpu_jobs > self.outer_workers:
            raise ValueError("max_heavy_cpu_jobs cannot exceed outer_workers")
        if self.max_gpu_jobs > self.outer_workers:
            raise ValueError("max_gpu_jobs cannot exceed outer_workers")
        if self.email_enabled and not self.email_to:
            raise ValueError("email_to cannot be empty when email_enabled=true")
        if self.native_device == "cuda" and self.max_gpu_jobs < 1:
            raise ValueError("native_device=cuda requires max_gpu_jobs >= 1")
        if self.gpu_priority and not self.gpu_backends:
            raise ValueError("gpu_backends cannot be empty when gpu_priority=true")
        return self

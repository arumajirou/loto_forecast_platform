"""Strict contracts for the local NeuralForecast FreTS extension."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0.0"
MODEL_ID = "nf-local-auto-frets"
UPSTREAM_REPOSITORY = "thuml/Time-Series-Library"
UPSTREAM_REVISION = "4e938a1767106324dd753b2a44832bf870a0252e"
UPSTREAM_SOURCE_PATH = "models/FreTS.py"
UPSTREAM_SOURCE_GIT_BLOB = "ca4e0b648db42a1846b7a0a9a661a39177f47005"
UPSTREAM_LICENSE = "MIT"
FRETS_EMBED_SIZE = 128
FRETS_HIDDEN_SIZE = 256
FRETS_SPARSITY_THRESHOLD = 0.01
FRETS_SCALE = 0.02
FRETS_CHANNEL_INDEPENDENCE = "1"
FRETS_PRECISION = "32-true"


class ArchitectureProfile(StrEnum):
    COMPACT = "compact"
    BALANCED = "balanced"
    WIDE = "wide"


class TrainingProfile(StrEnum):
    SMOKE = "smoke"
    STANDARD = "standard"
    EXTENDED = "extended"


class ArchitectureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    profile: ArchitectureProfile
    h: int = Field(gt=0)
    input_size: int = Field(ge=4, le=256)
    embed_size: int = Field(default=FRETS_EMBED_SIZE)
    hidden_size: int = Field(default=FRETS_HIDDEN_SIZE)
    sparsity_threshold: float = Field(default=FRETS_SPARSITY_THRESHOLD)
    scale: float = Field(default=FRETS_SCALE)
    channel_independence: str = Field(default=FRETS_CHANNEL_INDEPENDENCE)
    precision: str = Field(default=FRETS_PRECISION)
    temporal_fft_bins: int = Field(gt=0)
    expected_parameter_count: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_geometry(self) -> ArchitectureSpec:
        if self.embed_size != FRETS_EMBED_SIZE:
            raise ValueError("FreTS embed_size must remain 128")
        if self.hidden_size != FRETS_HIDDEN_SIZE:
            raise ValueError("FreTS hidden_size must remain 256")
        if self.sparsity_threshold != FRETS_SPARSITY_THRESHOLD:
            raise ValueError("FreTS sparsity_threshold must remain 0.01")
        if self.scale != FRETS_SCALE:
            raise ValueError("FreTS scale must remain 0.02")
        if self.channel_independence != FRETS_CHANNEL_INDEPENDENCE:
            raise ValueError("NeuralForecast FreTS must remain position-univariate")
        if self.precision != FRETS_PRECISION:
            raise ValueError("FreTS v1 supports precision=32-true only")
        if self.temporal_fft_bins != self.input_size // 2 + 1:
            raise ValueError("temporal_fft_bins does not match input_size")
        expected = expected_parameter_count(self.input_size, self.h)
        if self.expected_parameter_count != expected:
            raise ValueError("expected_parameter_count does not match FreTS geometry")
        return self


class TrainingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    profile: TrainingProfile
    max_steps: int = Field(gt=0)
    val_check_steps: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_schedule(self) -> TrainingSpec:
        if self.val_check_steps > self.max_steps:
            raise ValueError("val_check_steps must not exceed max_steps")
        return self


class TrialParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    architecture_profile: ArchitectureProfile
    training_profile: TrainingProfile
    learning_rate: float = Field(gt=0.0, lt=1.0)
    batch_size: int = Field(gt=0)
    windows_batch_size: int = Field(gt=0)
    scaler_type: str
    random_seed: int = Field(gt=0)
    precision: str = FRETS_PRECISION

    @model_validator(mode="after")
    def validate_policy(self) -> TrialParameters:
        if self.scaler_type not in {"identity", "robust"}:
            raise ValueError("scaler_type must be identity or robust")
        if self.precision != FRETS_PRECISION:
            raise ValueError("FreTS v1 supports precision=32-true only")
        return self


def expected_parameter_count(input_size: int, h: int) -> int:
    if input_size < 4 or h < 1:
        raise ValueError("FreTS parameter geometry must be positive")
    return 66_432 + 32_768 * input_size + 257 * h


def resolve_architecture(
    h: int,
    profile: ArchitectureProfile | str,
) -> ArchitectureSpec:
    if not isinstance(h, int) or isinstance(h, bool) or h < 1:
        raise ValueError("h must be a positive integer")
    selected = ArchitectureProfile(profile)
    if selected is ArchitectureProfile.COMPACT:
        input_size = max(16, h * 8)
    elif selected is ArchitectureProfile.BALANCED:
        input_size = max(32, h * 16)
    else:
        input_size = max(64, h * 32)
    if input_size > 256:
        raise ValueError("resolved FreTS input_size exceeds the v1 resource bound")
    return ArchitectureSpec(
        profile=selected,
        h=h,
        input_size=input_size,
        temporal_fft_bins=input_size // 2 + 1,
        expected_parameter_count=expected_parameter_count(input_size, h),
    )


def resolve_training(profile: TrainingProfile | str) -> TrainingSpec:
    selected = TrainingProfile(profile)
    values = {
        TrainingProfile.SMOKE: (20, 5),
        TrainingProfile.STANDARD: (500, 50),
        TrainingProfile.EXTENDED: (1500, 100),
    }
    max_steps, val_check_steps = values[selected]
    return TrainingSpec(
        profile=selected,
        max_steps=max_steps,
        val_check_steps=val_check_steps,
    )

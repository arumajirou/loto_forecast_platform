"""Strict contracts for the local NeuralForecast SegRNN extension."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0.0"
MODEL_ID = "nf-local-auto-segrnn"
UPSTREAM_REPOSITORY = "thuml/Time-Series-Library"
UPSTREAM_REVISION = "4e938a1767106324dd753b2a44832bf870a0252e"
UPSTREAM_SOURCE_PATH = "models/SegRNN.py"
UPSTREAM_LICENSE = "MIT"


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
    input_size: int = Field(gt=0)
    seg_len: int = Field(gt=0)
    d_model: int = Field(gt=1)

    @model_validator(mode="after")
    def validate_geometry(self) -> ArchitectureSpec:
        if self.input_size % self.seg_len != 0:
            raise ValueError("input_size must be divisible by seg_len")
        if self.h % self.seg_len != 0:
            raise ValueError("h must be divisible by seg_len")
        if self.d_model % 2 != 0:
            raise ValueError("d_model must be even for position/channel embeddings")
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
    dropout: float = Field(ge=0.0, lt=0.5)
    scaler_type: str
    random_seed: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_scaler(self) -> TrialParameters:
        if self.scaler_type not in {"identity", "robust"}:
            raise ValueError("scaler_type must be identity or robust")
        return self


def _round_up(value: int, divisor: int) -> int:
    return ((value + divisor - 1) // divisor) * divisor


def _balanced_segment_length(h: int) -> int:
    for candidate in (8, 5, 4, 2, 1):
        if candidate <= h and h % candidate == 0:
            return candidate
    return 1


def resolve_architecture(
    h: int,
    profile: ArchitectureProfile | str,
) -> ArchitectureSpec:
    if not isinstance(h, int) or isinstance(h, bool) or h < 1:
        raise ValueError("h must be a positive integer")
    selected = ArchitectureProfile(profile)
    if selected is ArchitectureProfile.COMPACT:
        seg_len = 1
        input_size = max(16, h * 8)
        d_model = 16
    elif selected is ArchitectureProfile.BALANCED:
        seg_len = _balanced_segment_length(h)
        input_size = _round_up(max(32, h * 16), seg_len)
        d_model = 32
    else:
        seg_len = 1
        input_size = max(64, h * 32)
        d_model = 64
    return ArchitectureSpec(
        profile=selected,
        h=h,
        input_size=input_size,
        seg_len=seg_len,
        d_model=d_model,
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

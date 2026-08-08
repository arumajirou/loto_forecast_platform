"""Strict contracts for the local NeuralForecast SCINet extension."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0.0"
MODEL_ID = "nf-local-auto-scinet"
UPSTREAM_REPOSITORY = "thuml/Time-Series-Library"
UPSTREAM_REVISION = "4e938a1767106324dd753b2a44832bf870a0252e"
UPSTREAM_SOURCE_PATH = "models/SCINet.py"
UPSTREAM_SOURCE_GIT_BLOB = "740d0f7d88e8a94aa7fe12c745f0876af7b0fc08"
UPSTREAM_LICENSE = "MIT"
TARGET_NEURALFORECAST_VERSION = "3.2.0"

SCINET_TREE_LEVEL = 3
SCINET_KERNEL_SIZE = 5
SCINET_STACKS = 1
SCINET_DROPOUT = 0.0
SCINET_BLOCKS_PER_TREE = 15
SCINET_CAUSAL_BLOCKS_PER_SCI_BLOCK = 4
SCINET_MAX_INPUT_SIZE = 256


class ArchitectureProfile(str, Enum):
    COMPACT = "compact"
    BALANCED = "balanced"
    WIDE = "wide"


class TrainingProfile(str, Enum):
    SMOKE = "smoke"
    STANDARD = "standard"
    EXTENDED = "extended"


class ArchitectureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    profile: ArchitectureProfile
    h: int = Field(gt=0)
    input_size: int = Field(ge=8, le=SCINET_MAX_INPUT_SIZE)
    tree_level: int = Field(ge=0)
    kernel_size: int = Field(gt=0)
    stacks: int = Field(ge=1)
    dropout: float = Field(ge=0.0)
    sci_blocks: int = Field(gt=0)
    causal_conv_blocks: int = Field(gt=0)
    expected_parameter_count: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_geometry(self) -> ArchitectureSpec:
        if self.input_size % 8 != 0:
            raise ValueError("input_size must be divisible by 8")
        if self.tree_level != SCINET_TREE_LEVEL:
            raise ValueError("SCINet v1 fixes tree_level=3")
        if self.kernel_size != SCINET_KERNEL_SIZE:
            raise ValueError("SCINet v1 fixes kernel_size=5")
        if self.stacks != SCINET_STACKS:
            raise ValueError("SCINet v1 fixes stacks=1")
        if self.dropout != SCINET_DROPOUT:
            raise ValueError("SCINet v1 fixes effective dropout=0.0")
        if self.sci_blocks != SCINET_BLOCKS_PER_TREE:
            raise ValueError("SCINet v1 requires 15 SCI blocks")
        expected_causal = SCINET_BLOCKS_PER_TREE * SCINET_CAUSAL_BLOCKS_PER_SCI_BLOCK
        if self.causal_conv_blocks != expected_causal:
            raise ValueError("SCINet v1 requires 60 causal convolution blocks")
        if self.expected_parameter_count != expected_parameter_count(
            self.input_size,
            self.h,
        ):
            raise ValueError("SCINet parameter-count contract mismatch")
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

    @model_validator(mode="after")
    def validate_scaler(self) -> TrialParameters:
        if self.scaler_type not in {"identity", "robust"}:
            raise ValueError("scaler_type must be identity or robust")
        return self


def expected_parameter_count(input_size: int, h: int) -> int:
    if input_size < 8 or h < 1:
        raise ValueError("invalid SCINet geometry")
    tree_parameters = 720
    projection_parameters = input_size * (input_size + h)
    return tree_parameters + projection_parameters


def _round_up(value: int, divisor: int) -> int:
    return ((value + divisor - 1) // divisor) * divisor


def resolve_architecture(
    h: int,
    profile: ArchitectureProfile | str,
) -> ArchitectureSpec:
    if not isinstance(h, int) or isinstance(h, bool) or h < 1:
        raise ValueError("h must be a positive integer")
    selected = ArchitectureProfile(profile)
    multipliers = {
        ArchitectureProfile.COMPACT: (8, 8),
        ArchitectureProfile.BALANCED: (16, 16),
        ArchitectureProfile.WIDE: (32, 32),
    }
    minimum, multiplier = multipliers[selected]
    input_size = _round_up(max(minimum, h * multiplier), 8)
    if input_size > SCINET_MAX_INPUT_SIZE:
        raise ValueError(f"resolved input_size exceeds {SCINET_MAX_INPUT_SIZE}: {input_size}")
    return ArchitectureSpec(
        profile=selected,
        h=h,
        input_size=input_size,
        tree_level=SCINET_TREE_LEVEL,
        kernel_size=SCINET_KERNEL_SIZE,
        stacks=SCINET_STACKS,
        dropout=SCINET_DROPOUT,
        sci_blocks=SCINET_BLOCKS_PER_TREE,
        causal_conv_blocks=(SCINET_BLOCKS_PER_TREE * SCINET_CAUSAL_BLOCKS_PER_SCI_BLOCK),
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

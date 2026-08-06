from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.neuralforecast.auto_segrnn.contracts import (
    ArchitectureProfile,
    ArchitectureSpec,
    TrainingProfile,
    TrialParameters,
    resolve_architecture,
    resolve_training,
)


def test_architecture_profiles_support_formal_horizons() -> None:
    for horizon in (1, 2, 5):
        for profile in ArchitectureProfile:
            spec = resolve_architecture(horizon, profile)
            assert spec.h == horizon
            assert spec.input_size % spec.seg_len == 0
            assert horizon % spec.seg_len == 0
            assert spec.d_model % 2 == 0


def test_architecture_rejects_non_divisible_geometry() -> None:
    with pytest.raises(ValidationError):
        ArchitectureSpec(
            profile=ArchitectureProfile.COMPACT,
            h=5,
            input_size=16,
            seg_len=2,
            d_model=16,
        )


def test_training_profiles_bound_validation_checks() -> None:
    for profile in TrainingProfile:
        spec = resolve_training(profile)
        assert 1 <= spec.val_check_steps <= spec.max_steps


def test_trial_parameters_are_strict() -> None:
    with pytest.raises(ValidationError):
        TrialParameters(
            architecture_profile="compact",
            training_profile="smoke",
            learning_rate="0.001",
            batch_size=16,
            windows_batch_size=128,
            dropout=0.1,
            scaler_type="identity",
            random_seed=1,
        )


def test_trial_parameters_reject_unknown_scaler() -> None:
    with pytest.raises(ValidationError):
        TrialParameters(
            architecture_profile=ArchitectureProfile.COMPACT,
            training_profile=TrainingProfile.SMOKE,
            learning_rate=0.001,
            batch_size=16,
            windows_batch_size=128,
            dropout=0.1,
            scaler_type="standard",
            random_seed=1,
        )

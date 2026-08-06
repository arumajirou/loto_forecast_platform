from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.neuralforecast.auto_scinet.contracts import (
    ArchitectureProfile,
    ArchitectureSpec,
    TrialParameters,
    expected_parameter_count,
    resolve_architecture,
    resolve_training,
)


def test_architecture_profiles_are_bounded_and_divisible() -> None:
    compact = resolve_architecture(1, ArchitectureProfile.COMPACT)
    balanced = resolve_architecture(2, ArchitectureProfile.BALANCED)
    wide = resolve_architecture(3, ArchitectureProfile.WIDE)
    assert (compact.input_size, balanced.input_size, wide.input_size) == (8, 32, 96)
    assert all(item.input_size % 8 == 0 for item in (compact, balanced, wide))
    assert compact.sci_blocks == 15
    assert compact.causal_conv_blocks == 60


def test_parameter_formula_for_univariate_one_stack() -> None:
    assert expected_parameter_count(8, 2) == 800
    assert expected_parameter_count(16, 4) == 1040


def test_architecture_contract_rejects_geometry_drift() -> None:
    with pytest.raises(ValidationError):
        ArchitectureSpec(
            profile=ArchitectureProfile.COMPACT,
            h=1,
            input_size=8,
            tree_level=2,
            kernel_size=5,
            stacks=1,
            dropout=0.0,
            sci_blocks=15,
            causal_conv_blocks=60,
            expected_parameter_count=792,
        )


def test_trial_parameters_are_strict() -> None:
    with pytest.raises(ValidationError):
        TrialParameters(
            architecture_profile="compact",
            training_profile="smoke",
            learning_rate=0.001,
            batch_size=32,
            windows_batch_size=128,
            scaler_type="standard",
            random_seed=1,
        )


def test_training_profiles_bound_validation_schedule() -> None:
    for profile in ("smoke", "standard", "extended"):
        resolved = resolve_training(profile)
        assert resolved.val_check_steps <= resolved.max_steps


def test_oversized_architecture_is_rejected() -> None:
    with pytest.raises(ValueError, match="exceeds 256"):
        resolve_architecture(20, "wide")

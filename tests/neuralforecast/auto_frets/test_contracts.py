from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.neuralforecast.auto_frets.contracts import (
    ArchitectureProfile,
    ArchitectureSpec,
    TrialParameters,
    expected_parameter_count,
    resolve_architecture,
    resolve_training,
)


def test_architecture_profiles_preserve_upstream_constants() -> None:
    compact = resolve_architecture(1, ArchitectureProfile.COMPACT)
    balanced = resolve_architecture(2, ArchitectureProfile.BALANCED)
    wide = resolve_architecture(5, ArchitectureProfile.WIDE)
    assert (compact.input_size, balanced.input_size, wide.input_size) == (16, 32, 160)
    for spec in (compact, balanced, wide):
        assert spec.embed_size == 128
        assert spec.hidden_size == 256
        assert spec.sparsity_threshold == 0.01
        assert spec.scale == 0.02
        assert spec.channel_independence == "1"
        assert spec.precision == "32-true"
        assert spec.temporal_fft_bins == spec.input_size // 2 + 1


def test_parameter_formula_matches_pinned_contract() -> None:
    assert expected_parameter_count(8, 2) == 329_090
    spec = resolve_architecture(2, ArchitectureProfile.COMPACT)
    assert spec.expected_parameter_count == expected_parameter_count(16, 2)


def test_contracts_fail_closed() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        resolve_architecture(0, "compact")
    with pytest.raises(ValueError, match="resource bound"):
        resolve_architecture(16, "wide")
    with pytest.raises(ValidationError):
        ArchitectureSpec(
            profile=ArchitectureProfile.COMPACT,
            h=1,
            input_size=16,
            embed_size=64,
            temporal_fft_bins=9,
            expected_parameter_count=expected_parameter_count(16, 1),
        )
    with pytest.raises(ValidationError):
        TrialParameters(
            architecture_profile=ArchitectureProfile.COMPACT,
            training_profile="smoke",
            learning_rate=1e-3,
            batch_size=16,
            windows_batch_size=64,
            scaler_type="standard",
            random_seed=1,
        )


def test_training_profiles_have_bounded_validation_schedule() -> None:
    for profile in ("smoke", "standard", "extended"):
        spec = resolve_training(profile)
        assert 0 < spec.val_check_steps <= spec.max_steps

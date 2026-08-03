from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from loto.game.geometry import geometry_for
from loto.probabilistic.compatibility import decide_compatibility
from loto.probabilistic.contracts import (
    NativeFitContext,
    NativePredictiveResult,
    ProbabilisticModelSpec,
    ProbabilisticRunConfig,
    TargetMode,
)
from loto.probabilistic.dataset import bundle_from_frame, synthetic_dataset, task_arrays
from loto.probabilistic.statuses import CompatibilityReason, TrialStatus


@pytest.mark.parametrize("game", ["mini", "loto6", "loto7"])
def test_select_target_contracts(game: str) -> None:
    bundle = synthetic_dataset(game, rows=12, seed=7)
    assert bundle.set_cardinality == bundle.geometry.positions
    assert bundle.candidate_indicator is not None
    assert bundle.candidate_indicator.shape == (12, bundle.geometry.universe_size)
    assert np.all(bundle.candidate_indicator.sum(axis=1) == bundle.geometry.positions)
    assert bundle.set_members is not None
    assert all(len(set(row)) == bundle.geometry.positions for row in bundle.set_members)
    target, classes = task_arrays(bundle, TargetMode.FIXED_CARDINALITY_SUBSET)
    assert classes == bundle.geometry.universe_size
    assert np.array_equal(target, bundle.candidate_indicator)


@pytest.mark.parametrize("game", ["numbers3", "numbers4"])
def test_digit_target_contracts(game: str) -> None:
    bundle = synthetic_dataset(game, rows=12, seed=9)
    assert bundle.position_tokens is not None
    assert bundle.position_tokens.shape == (12, bundle.geometry.positions)
    assert bundle.joint_tokens is not None
    assert all(len(token) == bundle.geometry.positions for token in bundle.joint_tokens)
    for mode in (
        TargetMode.CATEGORICAL_CONTEXT,
        TargetMode.DYNAMIC_MULTINOMIAL,
        TargetMode.JOINT_DISCRETE_COPULA,
        TargetMode.ONLINE_CHANGEPOINT,
    ):
        target, classes = task_arrays(bundle, mode)
        assert target.shape == (12, bundle.geometry.positions)
        assert classes == 10


def test_invalid_select_duplicate_is_rejected() -> None:
    frame = pd.DataFrame({"n1": [1], "n2": [1], "n3": [3], "n4": [4], "n5": [5]})
    with pytest.raises(ValueError, match="distinct"):
        bundle_from_frame(frame, game="mini")


def test_invalid_digit_range_is_rejected() -> None:
    frame = pd.DataFrame({"d1": [0], "d2": [10], "d3": [2]})
    with pytest.raises(ValueError, match="outside"):
        bundle_from_frame(frame, game="numbers3")


def test_draw_order_requires_explicit_verified_columns() -> None:
    frame = pd.DataFrame(
        {
            "n1": [1],
            "n2": [2],
            "n3": [3],
            "n4": [4],
            "n5": [5],
            "order1": [5],
            "order2": [1],
            "order3": [4],
            "order4": [2],
            "order5": [3],
        }
    )
    with pytest.raises(ValueError, match="explicit draw_order_columns"):
        bundle_from_frame(frame, game="mini", draw_order_verified=True)
    unverified = bundle_from_frame(
        frame,
        game="mini",
        draw_order_columns=[f"order{i}" for i in range(1, 6)],
    )
    with pytest.raises(ValueError, match="verified draw order"):
        task_arrays(unverified, TargetMode.ORDERED_WITHOUT_REPLACEMENT)
    verified = bundle_from_frame(
        frame,
        game="mini",
        draw_order_columns=[f"order{i}" for i in range(1, 6)],
        draw_order_verified=True,
    )
    target, classes = task_arrays(verified, TargetMode.ORDERED_WITHOUT_REPLACEMENT)
    assert classes == 31
    assert target.tolist() == [[4, 0, 3, 1, 2]]


def test_draw_order_must_match_result_set() -> None:
    frame = pd.DataFrame(
        {
            "n1": [1], "n2": [2], "n3": [3], "n4": [4], "n5": [5],
            "o1": [1], "o2": [2], "o3": [3], "o4": [4], "o5": [6],
        }
    )
    with pytest.raises(ValueError, match="does not match"):
        bundle_from_frame(
            frame,
            game="mini",
            draw_order_columns=[f"o{i}" for i in range(1, 6)],
            draw_order_verified=True,
        )


def test_ordered_model_is_fail_closed_without_verified_order() -> None:
    spec = ProbabilisticModelSpec(
        schema_version="1.0.0",
        model_id="test-ordered",
        family="ranking",
        role="research",
        likelihood="PlackettLuce",
        latent_structure="ordered without replacement",
        backends=("builtin",),
        tasks=(TargetMode.ORDERED_WITHOUT_REPLACEMENT,),
        priority="p2",
        supports_exogenous=False,
        hierarchical=False,
        dynamic=False,
        experimental=True,
    )
    denied = decide_compatibility(
        spec,
        geometry=geometry_for("mini"),
        draw_order_verified=False,
    )
    assert not denied.allowed
    assert denied.reason_code == CompatibilityReason.DRAW_ORDER_REQUIRED
    allowed = decide_compatibility(
        spec,
        geometry=geometry_for("mini"),
        draw_order_verified=True,
    )
    assert allowed.allowed


def test_target_mode_config_round_trip_and_unknown_fail_closed() -> None:
    config = ProbabilisticRunConfig.model_validate(
        {"target_modes": ["fixed_cardinality_subset", "online_changepoint"]}
    )
    restored = ProbabilisticRunConfig.model_validate(config.model_dump(mode="json"))
    assert restored == config
    with pytest.raises(ValidationError):
        ProbabilisticRunConfig.model_validate({"unknown_ppl02_parameter": True})
    with pytest.raises(ValidationError, match="duplicates"):
        ProbabilisticRunConfig.model_validate(
            {"target_modes": ["online_changepoint", "online_changepoint"]}
        )


def test_new_result_contracts_and_statuses() -> None:
    context = NativeFitContext(
        trial_id="trial-1",
        game="numbers3",
        target_mode=TargetMode.CATEGORICAL_CONTEXT,
        train_end=80,
        seed=42,
        feature_set_hash="abc",
        data_version="v1",
    )
    result = NativePredictiveResult(point_prediction=[1, 2, 3])
    assert context.train_end == 80
    assert result.diagnostics == {}
    assert TrialStatus.RESEARCH_NO_GAIN.value == "RESEARCH_NO_GAIN"
    assert TrialStatus.DRAW_ORDER_REQUIRED.value == "DRAW_ORDER_REQUIRED"

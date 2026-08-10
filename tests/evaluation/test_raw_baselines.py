from __future__ import annotations

import numpy as np

from loto.evaluation.metric_registry import (
    REQUIRED_BASELINE_IDS,
)
from loto.evaluation.raw_baselines import (
    predict_raw_baselines,
    stable_target_seed,
)


def _numbers3_history() -> np.ndarray:
    return np.asarray(
        [
            [
                draw % 10,
                (draw + 3) % 10,
                (draw + 6) % 10,
            ]
            for draw in range(120)
        ],
        dtype=float,
    )


def test_raw_baseline_inventory_and_repeatability() -> None:
    history = _numbers3_history()
    seeds = (42, 1729, 20260730)

    left = predict_raw_baselines(
        history,
        game_id="numbers3",
        target_draw_no=121,
        seeds=seeds,
    )

    right = predict_raw_baselines(
        history,
        game_id="numbers3",
        target_draw_no=121,
        seeds=seeds,
    )

    assert left == right
    assert len(left) == 9

    assert {
        item.baseline_id
        for item in left
    } == set(REQUIRED_BASELINE_IDS)

    random = [
        item
        for item in left
        if item.baseline_id == "random"
    ]

    assert [
        item.seed
        for item in random
    ] == list(seeds)

    deterministic = [
        item
        for item in left
        if item.baseline_id != "random"
    ]

    assert all(
        item.seed is None
        for item in deterministic
    )


def test_fixed_digit_baseline_remains_raw_float() -> None:
    predictions = predict_raw_baselines(
        _numbers3_history(),
        game_id="numbers3",
        target_draw_no=121,
        seeds=(42,),
    )

    fixed = next(
        item
        for item in predictions
        if item.baseline_id == "fixed"
    )

    assert fixed.values == (
        4.5,
        4.5,
        4.5,
    )


def test_target_seed_is_schedule_independent() -> None:
    assert stable_target_seed(
        42,
        "numbers3",
        121,
    ) == stable_target_seed(
        42,
        "numbers3",
        121,
    )

    assert stable_target_seed(
        42,
        "numbers3",
        121,
    ) != stable_target_seed(
        42,
        "numbers3",
        122,
    )

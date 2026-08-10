from __future__ import annotations

from itertools import combinations

import numpy as np
import pytest

from loto.evaluation.theory_general import position_pmf, theoretical_bounds
from loto.game.geometry import GameGeometry, geometry_for
from loto.probabilistic.decoder import (
    DecodeObjective,
    build_within_tau_utility,
    decode_select_distribution,
    decode_select_positions,
)


def _pmf_matrix(geometry: GameGeometry) -> np.ndarray:
    pmf = position_pmf(geometry)
    return np.asarray(
        [
            [float(pmf[slot][value]) for value in geometry.values]
            for slot in range(1, geometry.positions + 1)
        ],
        dtype=float,
    )


@pytest.mark.parametrize(
    ("game", "expected", "expected_hit"),
    [
        ("mini", [2, 8, 16, 24, 30], 0.29409396684146405),
        ("loto6", [2, 9, 18, 26, 35, 42], 0.23501935168651591),
        ("loto7", [2, 7, 13, 19, 25, 31, 36], 0.2922598539296832),
        ("bingo5", [2, 6, 12, 18, 23, 29, 35, 39], 0.28949324738798426),
    ],
)
def test_within_tau_decoder_reproduces_exact_iid_null_optimum(
    game: str, expected: list[int], expected_hit: float
) -> None:
    geometry = geometry_for(game)
    probabilities = _pmf_matrix(geometry)

    decoded = decode_select_distribution(
        probabilities,
        geometry,
        objective=DecodeObjective.WITHIN_TAU,
        tau=1,
    )

    assert decoded == expected
    geometry.validate_outcome(decoded)
    utility = build_within_tau_utility(probabilities, geometry, tau=1)
    indexes = [value - geometry.value_min for value in decoded]
    achieved = float(np.mean([utility[position, index] for position, index in enumerate(indexes)]))
    assert achieved == pytest.approx(expected_hit)
    assert achieved == pytest.approx(theoretical_bounds(geometry, tau=1).within_tau_ceiling)


def test_within_tau_decoder_matches_bruteforce_on_small_geometry() -> None:
    geometry = GameGeometry(
        key="small-select",
        family="select",
        positions=3,
        value_min=1,
        value_max=6,
    )
    probabilities = np.asarray(
        [
            [0.30, 0.25, 0.20, 0.10, 0.10, 0.05],
            [0.05, 0.10, 0.25, 0.30, 0.20, 0.10],
            [0.02, 0.03, 0.10, 0.20, 0.30, 0.35],
        ],
        dtype=float,
    )
    utility = build_within_tau_utility(probabilities, geometry, tau=1)

    decoded = decode_select_distribution(
        probabilities,
        geometry,
        objective=DecodeObjective.WITHIN_TAU,
        tau=1,
    )

    candidates: list[tuple[float, tuple[int, ...]]] = []
    for values in combinations(geometry.values, geometry.positions):
        score = sum(
            float(utility[position, value - geometry.value_min])
            for position, value in enumerate(values)
        )
        candidates.append((score, values))
    best_score = max(score for score, _ in candidates)
    expected = min(values for score, values in candidates if np.isclose(score, best_score))
    assert tuple(decoded) == expected


def test_map_compatibility_api_keeps_existing_semantics() -> None:
    geometry = geometry_for("mini")
    probabilities = _pmf_matrix(geometry)

    assert decode_select_positions(probabilities, geometry) == decode_select_distribution(
        probabilities,
        geometry,
        objective=DecodeObjective.MAP,
    )


def test_within_tau_probability_validation_fails_closed() -> None:
    geometry = geometry_for("mini")
    probabilities = _pmf_matrix(geometry)

    bad = probabilities.copy()
    bad[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        decode_select_distribution(bad, geometry, objective=DecodeObjective.WITHIN_TAU)

    bad = probabilities.copy()
    bad[0, 0] = -0.1
    with pytest.raises(ValueError, match="non-negative"):
        decode_select_distribution(bad, geometry, objective=DecodeObjective.WITHIN_TAU)

    with pytest.raises(ValueError, match="tau must be >= 0"):
        decode_select_distribution(
            probabilities,
            geometry,
            objective=DecodeObjective.WITHIN_TAU,
            tau=-1,
        )

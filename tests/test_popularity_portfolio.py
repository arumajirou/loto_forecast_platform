from __future__ import annotations

import numpy as np
import pytest

from loto.game.geometry import geometry_for
from loto.strategy.portfolio import optimize_portfolio_cpsat, optimize_portfolio_greedy


def test_greedy_prefers_lower_popularity_risk_when_coverage_gain_ties() -> None:
    geometry = geometry_for("mini")
    targets = np.asarray([[1, 5, 10, 20, 30]], dtype=int)
    candidates = [
        [1, 5, 10, 20, 30],
        [1, 5, 10, 20, 31],
        [2, 6, 11, 21, 30],
    ]
    risks = [20.0, 2.0, 5.0]

    result = optimize_portfolio_greedy(
        targets,
        candidates,
        risks,
        geometry,
        budget=1,
        tolerance=1,
        popularity_weight=0.2,
    )

    assert result.selected_indices == (1,)
    assert result.coverage == pytest.approx(1.0)
    assert result.mean_q95_co_winner_risk == pytest.approx(2.0)
    assert result.method == "greedy-popularity-coverage-v1"


def test_greedy_portfolio_respects_budget_legality_and_reports_overlap() -> None:
    geometry = geometry_for("mini")
    targets = np.asarray(
        [
            [1, 5, 10, 20, 30],
            [2, 6, 11, 21, 31],
            [3, 7, 12, 22, 29],
        ],
        dtype=int,
    )
    candidates = targets.tolist() + [[4, 8, 13, 23, 28]]
    risks = [4.0, 3.0, 2.0, 1.0]

    result = optimize_portfolio_greedy(
        targets,
        candidates,
        risks,
        geometry,
        budget=2,
        tolerance=0,
        popularity_weight=0.01,
        overlap_weight=0.1,
    )

    assert len(result.tickets) == 2
    assert 0.0 <= result.coverage <= 1.0
    assert 0.0 <= result.max_pair_overlap_fraction <= 1.0
    for ticket in result.tickets:
        geometry.validate_outcome(list(ticket))


def test_portfolio_inputs_fail_closed() -> None:
    geometry = geometry_for("mini")
    targets = np.asarray([[1, 5, 10, 20, 30]], dtype=int)
    candidates = [[1, 5, 10, 20, 30]]

    with pytest.raises(ValueError, match="budget"):
        optimize_portfolio_greedy(targets, candidates, [1.0], geometry, budget=0)
    with pytest.raises(ValueError, match="align"):
        optimize_portfolio_greedy(targets, candidates, [1.0, 2.0], geometry, budget=1)
    with pytest.raises(ValueError, match="duplicate"):
        optimize_portfolio_greedy(
            targets,
            [candidates[0], candidates[0]],
            [1.0, 2.0],
            geometry,
            budget=1,
        )


def test_cpsat_optional_backend_obeys_budget_when_available() -> None:
    pytest.importorskip("ortools.sat.python.cp_model")
    geometry = geometry_for("mini")
    targets = np.asarray(
        [
            [1, 5, 10, 20, 30],
            [2, 6, 11, 21, 31],
        ],
        dtype=int,
    )
    candidates = targets.tolist() + [[3, 7, 12, 22, 29]]

    result = optimize_portfolio_cpsat(
        targets,
        candidates,
        [5.0, 2.0, 1.0],
        geometry,
        budget=1,
        tolerance=0,
        time_limit_seconds=5.0,
        workers=1,
    )

    assert len(result.tickets) <= 1
    assert result.method.startswith("cpsat-popularity-coverage-v1:")

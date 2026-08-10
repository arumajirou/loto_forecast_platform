from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from loto.decoding.hybrid import decode_hybrid
from loto.evaluation.metrics import evaluate_draws, evaluate_outcomes
from loto.game.geometry import geometry_for, known_games


def _legal_row(game: str) -> list[int]:
    geometry = geometry_for(game)
    if geometry.family == "select":
        return list(range(geometry.value_min, geometry.value_min + geometry.positions))
    return [geometry.value_min] * geometry.positions


@pytest.mark.parametrize("game", known_games())
def test_evaluate_outcomes_accepts_every_canonical_geometry(game: str) -> None:
    row = _legal_row(game)
    actual = np.asarray([row, row], dtype=int)
    predicted = actual.copy()

    result = evaluate_outcomes(actual, predicted, game, tau=1)

    assert result["position_mae"] == pytest.approx(0.0)
    assert result["position_mse"] == pytest.approx(0.0)
    assert result["position_rmse"] == pytest.approx(0.0)
    assert result["within_tau_rate"] == pytest.approx(1.0)
    assert result["all_positions_within_tau_rate"] == pytest.approx(1.0)


def test_evaluate_outcomes_rejects_geometry_width_mismatch() -> None:
    actual = np.ones((2, 3), dtype=int)
    predicted = actual.copy()
    with pytest.raises(ValueError, match="game='loto6'"):
        evaluate_outcomes(actual, predicted, "loto6")


def test_evaluate_draws_keeps_loto7_legacy_keys() -> None:
    row = _legal_row("loto7")
    actual = np.asarray([row], dtype=int)
    result = evaluate_draws(actual, actual.copy(), tau=1)

    assert set(result) == {"mean_hits_at_7", "position_mae", "position_mse", "within_1_rate"}
    assert result["mean_hits_at_7"] == pytest.approx(geometry_for("loto7").positions)
    assert result["within_1_rate"] == pytest.approx(1.0)


def test_legacy_hybrid_derives_numeric_dimensions_from_game_geometry() -> None:
    geometry = geometry_for("loto7")
    candidate_scores = np.zeros(geometry.universe_size, dtype=float)
    position_scores = np.zeros((geometry.positions, geometry.universe_size), dtype=float)

    decoded = decode_hybrid(candidate_scores, position_scores, top_k=1)

    assert len(decoded) == 1
    assert decoded[0].numbers == list(
        range(geometry.value_min, geometry.value_min + geometry.positions)
    )


def test_legacy_hybrid_contains_no_canonical_universe_integer_literals() -> None:
    import loto.decoding.hybrid as hybrid

    path = Path(hybrid.__file__).resolve()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    }
    assert not constants.intersection({31, 37, 40, 43})

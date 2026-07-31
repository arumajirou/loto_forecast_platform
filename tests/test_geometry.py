"""Geometry is the single source of truth for every game shape."""

import ast
from pathlib import Path

import pytest

from loto.game.geometry import geometry_for, known_games


def test_all_six_games_present():
    assert known_games() == ["bingo5", "loto6", "loto7", "mini", "numbers3", "numbers4"]


@pytest.mark.parametrize(
    ("game", "positions", "lo", "hi", "family"),
    [
        ("mini", 5, 1, 31, "select"),
        ("loto6", 6, 1, 43, "select"),
        ("loto7", 7, 1, 37, "select"),
        ("bingo5", 8, 1, 40, "select"),
        ("numbers3", 3, 0, 9, "digits"),
        ("numbers4", 4, 0, 9, "digits"),
    ],
)
def test_geometry_values(game, positions, lo, hi, family):
    g = geometry_for(game)
    assert (g.positions, g.value_min, g.value_max, g.family) == (positions, lo, hi, family)


def test_outcome_space_matches_published_odds():
    # published 1-in-N jackpot odds
    assert geometry_for("loto7").outcome_space == 10_295_472
    assert geometry_for("loto6").outcome_space == 6_096_454
    assert geometry_for("mini").outcome_space == 169_911
    assert geometry_for("numbers4").outcome_space == 10_000
    assert geometry_for("numbers3").outcome_space == 1_000


def test_select_games_reject_illegal_outcomes():
    g = geometry_for("loto7")
    g.validate_outcome([1, 2, 3, 4, 5, 6, 7])
    with pytest.raises(ValueError, match="ascending"):
        g.validate_outcome([7, 6, 5, 4, 3, 2, 1])
    with pytest.raises(ValueError, match="outside"):
        g.validate_outcome([1, 2, 3, 4, 5, 6, 38])
    with pytest.raises(ValueError, match="expected 7"):
        g.validate_outcome([1, 2, 3])


def test_digit_games_allow_repeats_and_leading_zero():
    g = geometry_for("numbers3")
    g.validate_outcome([0, 0, 0])
    g.validate_outcome([9, 0, 9])
    assert not g.ascending and not g.distinct


def test_inclusion_vector_length_differs_by_family():
    assert geometry_for("loto7").inclusion_vector_length == 37
    assert geometry_for("numbers4").inclusion_vector_length == 40  # 4 slots x 10 digits


def test_marginal_base_rate():
    assert geometry_for("loto7").marginal_base_rate() == pytest.approx(7 / 37)
    assert geometry_for("numbers3").marginal_base_rate() == pytest.approx(0.1)


def test_geometry_rejects_impossible_configuration():
    from loto.game.geometry import GameGeometry

    with pytest.raises(ValueError, match="cannot draw"):
        GameGeometry(key="bad", family="select", positions=50, value_min=1, value_max=10)


def test_no_hardcoded_geometry_outside_game_package():
    """Constitution gate IV: universe sizes may not appear as literals outside ``loto.game``.

    Uses the AST rather than a text scan so that prose in docstrings (which legitimately
    discusses the v2.1.0 hard-coding defect) cannot trip the gate, while an actual integer
    literal anywhere in the code does.
    """
    forbidden = {31, 37, 40, 43}
    root = Path(__file__).resolve().parents[1] / "src" / "loto"
    v3_modules = [
        root / "evaluation" / "theory_general.py",
        root / "evaluation" / "metrics_general.py",
        root / "evaluation" / "protocol.py",
        root / "evaluation" / "leaderboard.py",
        root / "contracts_general.py",
        root / "orchestration" / "research_v3.py",
        root / "reconciliation" / "hierarchy.py",
    ]
    offenders: dict[str, list[tuple[int, int]]] = {}
    for path in v3_modules:
        assert path.is_file(), f"expected v3 module missing: {path}"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, int):
                if node.value in forbidden and not isinstance(node.value, bool):
                    offenders.setdefault(path.name, []).append(
                        (getattr(node, "lineno", -1), node.value)
                    )
    assert not offenders, f"hard-coded geometry literals found: {offenders}"

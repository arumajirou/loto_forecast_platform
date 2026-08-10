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


def _inside_len_comparison(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    current = parents.get(node)
    while current is not None and not isinstance(current, ast.stmt):
        if isinstance(current, ast.Compare):
            expressions = [current.left, *current.comparators]
            return any(
                isinstance(expression, ast.Call)
                and isinstance(expression.func, ast.Name)
                and expression.func.id == "len"
                for expression in expressions
            )
        current = parents.get(current)
    return False


def _reviewed_non_geometry_exception(relative: str, node: ast.Constant, source_line: str) -> bool:
    """Narrow reviewed exceptions for constants that numerically equal a game universe."""
    return (
        relative == "probabilistic/models/reference.py"
        and node.value == 40
        and "receptive = max(window * 2, 40)" in source_line
    )


def test_no_hardcoded_universe_sizes_in_geometry_sensitive_packages():
    """Constitution gate IV: production universe sizes come from ``loto.game``.

    The previous gate scanned seven hand-written files only, so new evaluation/decoder modules
    could silently reintroduce Loto-specific dimensions. Scan the geometry-sensitive packages
    recursively. Draw-size literals such as 3/4/5/6/7/8 are intentionally not scanned because
    they are common algorithmic constants; those are covered by dynamic all-game shape tests.

    SHA-1 lengths are structurally excluded when the literal is part of a ``len(...)`` comparison.
    Any other same-valued non-geometry constant requires a narrow reviewed exception.
    """
    forbidden = {31, 37, 40, 43}
    root = Path(__file__).resolve().parents[1] / "src" / "loto"
    package_roots = [
        root / "evaluation",
        root / "decoding",
        root / "probabilistic",
        root / "orchestration",
        root / "reconciliation",
    ]
    modules = [root / "contracts_general.py"]
    for package_root in package_roots:
        assert package_root.is_dir(), f"expected geometry-sensitive package missing: {package_root}"
        modules.extend(sorted(package_root.rglob("*.py")))

    offenders: dict[str, list[tuple[int, int]]] = {}
    for path in modules:
        assert path.is_file(), f"expected module missing: {path}"
        source = path.read_text(encoding="utf-8")
        source_lines = source.splitlines()
        tree = ast.parse(source, filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        relative = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Constant)
                and isinstance(node.value, int)
                and not isinstance(node.value, bool)
                and node.value in forbidden
            ):
                continue
            if _inside_len_comparison(node, parents):
                continue
            line_number = getattr(node, "lineno", -1)
            source_line = source_lines[line_number - 1] if line_number > 0 else ""
            if _reviewed_non_geometry_exception(relative, node, source_line):
                continue
            offenders.setdefault(relative, []).append((line_number, node.value))
    assert not offenders, f"hard-coded geometry literals found: {offenders}"

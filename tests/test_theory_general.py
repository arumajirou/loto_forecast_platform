"""Exact theoretical bounds, verified against independently known values."""
import pytest

from loto.evaluation.theory_general import bounds_table, position_pmf, theoretical_bounds
from loto.game.geometry import geometry_for, known_games


def test_loto7_mae_floor_is_exactly_known_value():
    # independently derived value for the 7-of-37 order-statistic median predictor
    assert theoretical_bounds("loto7").mae_floor == pytest.approx(3.8337, abs=1e-4)


def test_digit_game_bounds_are_closed_form():
    b = theoretical_bounds("numbers3")
    # median of U{0..9} gives E|U - 4| = 2.5 ; Var = 8.25, mean predictor 4 or 5 -> 8.5
    assert b.mae_floor == pytest.approx(2.5)
    assert b.mse_floor == pytest.approx(8.5)
    assert b.within_tau_ceiling == pytest.approx(0.3)


@pytest.mark.parametrize("game", known_games())
def test_pmf_normalised_for_every_slot(game):
    for row in position_pmf(geometry_for(game)).values():
        assert sum(row.values()) == 1


@pytest.mark.parametrize("game", known_games())
def test_mae_optimal_predictor_is_legal(game):
    assert theoretical_bounds(game).legal_median


@pytest.mark.parametrize("game", [g for g in known_games() if geometry_for(g).family == "select"])
def test_metric_tradeoff_is_strict_for_select_games(game):
    """The hit-rate-optimal predictor MUST be worse on MAE, and vice versa.

    This is the property that makes single-metric leaderboards misleading.
    """
    b = theoretical_bounds(game)
    assert b.tau_mae > b.mae_floor
    assert b.median_within_tau < b.within_tau_ceiling


def test_expected_hits_matches_hypergeometric_mean():
    b = theoretical_bounds("loto7")
    assert b.expected_hits == pytest.approx(7 * 7 / 37)


def test_bounds_table_covers_all_games():
    assert len(bounds_table()) == len(known_games())


def test_negative_tau_rejected():
    with pytest.raises(ValueError, match="tau"):
        theoretical_bounds("loto7", tau=-1)

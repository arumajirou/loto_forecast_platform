"""Contracts must be parameterised by geometry, not pinned to Loto7."""
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from loto.contracts_general import SCHEMA_VERSION, contracts_for
from loto.game.geometry import geometry_for, known_games


@pytest.mark.parametrize("game", known_games())
def test_contracts_build_for_every_game(game):
    c = contracts_for(game)
    g = geometry_for(game)
    described = c.describe()
    assert described["positions"] == g.positions
    assert described["value_range"] == [g.value_min, g.value_max]
    assert described["schema_version"] == SCHEMA_VERSION


def test_contracts_are_cached():
    assert contracts_for("loto7") is contracts_for("loto7")


def test_unknown_game_is_rejected():
    with pytest.raises(ValueError, match="unknown game"):
        contracts_for("toto")


def test_loto6_accepts_its_own_width_and_range():
    c = contracts_for("loto6")
    combo = c.DecodedCombination(values=[1, 5, 12, 20, 33, 43], score=0.5)
    assert combo.values[-1] == 43


def test_loto6_rejects_a_value_above_its_own_universe():
    """43 is legal for loto6; 44 is not. v1 contracts capped everything at 37."""
    c = contracts_for("loto6")
    with pytest.raises(ValidationError):
        c.DecodedCombination(values=[1, 5, 12, 20, 33, 44], score=0.5)


def test_loto7_still_rejects_38():
    c = contracts_for("loto7")
    with pytest.raises(ValidationError):
        c.DecodedCombination(values=[1, 2, 3, 4, 5, 6, 38], score=0.0)


def test_wrong_width_is_rejected():
    c = contracts_for("mini")
    with pytest.raises(ValidationError):
        c.DecodedCombination(values=[1, 2, 3], score=0.0)


def test_non_ascending_select_combination_is_rejected():
    c = contracts_for("bingo5")
    with pytest.raises(ValidationError):
        c.DecodedCombination(values=[8, 7, 6, 5, 4, 3, 2, 1], score=0.0)


def test_digit_game_allows_repeats_and_leading_zeros():
    c = contracts_for("numbers4")
    combo = c.DecodedCombination(values=[0, 0, 7, 7], score=1.0)
    assert combo.values == [0, 0, 7, 7]


def test_digit_game_rejects_a_two_digit_value():
    c = contracts_for("numbers3")
    with pytest.raises(ValidationError):
        c.DecodedCombination(values=[0, 0, 10], score=1.0)


def test_position_bound_follows_the_game_slot_count():
    c = contracts_for("mini")
    c.PositionProbability(position=5, candidate_number=10, probability=0.1)
    with pytest.raises(ValidationError):
        c.PositionProbability(position=6, candidate_number=10, probability=0.1)


def test_candidate_probability_range_follows_the_universe():
    c = contracts_for("numbers3")
    c.CandidateProbability(candidate_number=0, probability=0.1, rank_score=1.0)
    with pytest.raises(ValidationError):
        c.CandidateProbability(candidate_number=10, probability=0.1, rank_score=1.0)


def _forecast_kwargs(game, **overrides):
    g = geometry_for(game)
    c = contracts_for(game)
    now = datetime.now(UTC)
    candidates = [
        c.CandidateProbability(candidate_number=v, probability=g.marginal_base_rate(),
                               rank_score=float(v))
        for v in g.values
    ] * (g.positions if g.family == "digits" else 1)
    values = (
        list(g.values)[: g.positions] if g.family == "select" else [0] * g.positions
    )
    kwargs = dict(
        forecast_id="f1", draw_id="d1", model_id="uniform", data_version="v1",
        feature_set_id="fs1", protocol_hash="a" * 64,
        created_at=now, draw_time=now + timedelta(days=1),
        combination=c.DecodedCombination(values=values, score=0.0),
        candidates=candidates,
    )
    kwargs.update(overrides)
    return c, kwargs


def test_forecast_package_accepts_a_complete_payload():
    c, kwargs = _forecast_kwargs("loto7")
    package = c.ForecastPackage(**kwargs)
    assert package.game == "loto7"
    assert len(package.candidates) == 37


def test_forecast_package_requires_the_full_inclusion_vector():
    c, kwargs = _forecast_kwargs("loto7")
    kwargs["candidates"] = kwargs["candidates"][:-1]
    with pytest.raises(ValidationError):
        c.ForecastPackage(**kwargs)


def test_forecast_must_predate_the_draw():
    c, kwargs = _forecast_kwargs("loto7")
    kwargs["draw_time"] = kwargs["created_at"]
    with pytest.raises(ValidationError, match="strictly before"):
        c.ForecastPackage(**kwargs)


def test_protocol_hash_must_be_a_sha256():
    c, kwargs = _forecast_kwargs("loto7", protocol_hash="tooshort")
    with pytest.raises(ValidationError):
        c.ForecastPackage(**kwargs)


def test_extra_fields_are_forbidden():
    c, kwargs = _forecast_kwargs("loto7", unexpected="x")
    with pytest.raises(ValidationError):
        c.ForecastPackage(**kwargs)


def test_digit_game_forecast_uses_the_flattened_vector_width():
    c, kwargs = _forecast_kwargs("numbers3")
    package = c.ForecastPackage(**kwargs)
    assert len(package.candidates) == geometry_for("numbers3").inclusion_vector_length == 30

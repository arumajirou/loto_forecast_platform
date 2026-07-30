"""End-to-end research run: every stage wired, every game supported."""
import numpy as np
import pandas as pd
import pytest

from loto.game.geometry import geometry_for, known_games
from loto.orchestration.research_v3 import (
    ResearchConfig,
    frequency_predictor,
    run_research,
    theory_median_predictor,
)


def _synthetic(game: str, n: int = 220, seed: int = 7) -> pd.DataFrame:
    g = geometry_for(game)
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        if g.family == "select":
            v = sorted(rng.choice(np.arange(g.value_min, g.value_max + 1),
                                  size=g.positions, replace=False).tolist())
        else:
            v = rng.integers(g.value_min, g.value_max + 1, size=g.positions).tolist()
        rows.append({"draw_no": i + 1, **dict(zip(g.column_names(), v))})
    return pd.DataFrame(rows)


def _cfg(game: str, **kw) -> ResearchConfig:
    base = dict(game=game, folds=4, test_size=10, min_train_size=80,
                holdout_size=20, n_boot=200, sentinel_repeats=3)
    base.update(kw)
    return ResearchConfig(**base)


@pytest.mark.parametrize("game", known_games())
def test_run_completes_for_every_game(game):
    out = run_research(_synthetic(game), _cfg(game), data_version=f"{game}-test")
    assert out.status in ("SUCCEEDED", "PARTIALLY_SUCCEEDED")
    assert len(out.protocol_hash) == 64
    assert out.geometry["key"] == game


def test_iid_data_yields_no_champion():
    out = run_research(_synthetic("loto7"), _cfg("loto7"))
    assert out.leaderboard["verdict"] == "NO_MODEL_BEATS_BASELINE"
    assert out.leaderboard["champion"] is None


def test_mandatory_controls_are_injected_even_when_not_requested():
    out = run_research(_synthetic("loto7"), _cfg("loto7"), predictors={})
    ids = {r["model_id"] for r in out.leaderboard["rows"]}
    assert {"position-median", "position-modal", "frequency"} <= ids
    assert any("mandatory controls injected" in w for w in out.warnings)


def test_holdout_is_never_evaluated_and_is_reported_as_sealed():
    out = run_research(_synthetic("loto7"), _cfg("loto7"))
    assert out.holdout_evaluated is False
    assert out.holdout_sealed is True
    assert out.holdout_rows == 20
    assert out.development_rows == 200


def test_every_leaderboard_row_carries_uncertainty():
    out = run_research(_synthetic("loto6"), _cfg("loto6"))
    for row in out.leaderboard["rows"]:
        assert row["n"] > 0
        assert row["adjusted_p"] is not None
        assert row["rank"] is not None


def test_protocol_hash_changes_with_horizon():
    a = run_research(_synthetic("loto7"), _cfg("loto7", horizon=1))
    b = run_research(_synthetic("loto7"), _cfg("loto7", horizon=4))
    assert a.protocol_hash != b.protocol_hash


def test_protocol_hash_is_reproducible():
    a = run_research(_synthetic("loto7"), _cfg("loto7"), data_version="fixed")
    b = run_research(_synthetic("loto7"), _cfg("loto7"), data_version="fixed")
    assert a.protocol_hash == b.protocol_hash


def test_sentinel_runs_and_is_recorded():
    out = run_research(_synthetic("loto7"), _cfg("loto7"))
    assert out.sentinel["status"] in ("SENTINEL_CLEAN", "SENTINEL_TRIPPED")
    assert out.stage_status["sentinel"].startswith(("SUCCEEDED", "PARTIAL"))


def test_conformal_interval_is_produced_and_covers():
    out = run_research(_synthetic("loto7"), _cfg("loto7", conformal_alpha=0.1))
    assert "coverage" in out.conformal
    assert out.conformal["coverage"]["coverage"] > 0.7


def test_pace_gate_is_wired_not_dead_code():
    out = run_research(_synthetic("loto7"), _cfg("loto7"))
    assert out.stage_status["pace_gate"].startswith("SUCCEEDED")
    assert out.pace["decision"] in ("COLLECTING", "INCONCLUSIVE", "ACCEPT")
    assert out.pace["protocol_hash"] == out.protocol_hash


def test_statistical_power_is_stated_honestly_for_a_tiny_sweep():
    out = run_research(_synthetic("loto7"), _cfg("loto7", folds=2, test_size=3))
    assert "below any reasonable detection threshold" in out.power_note


def test_a_failing_model_is_recorded_not_swallowed():
    def broken(train, geometry, n_test):
        raise RuntimeError("deliberate failure")

    out = run_research(_synthetic("loto7"), _cfg("loto7"), predictors={"broken": broken})
    assert out.status == "PARTIALLY_SUCCEEDED"
    assert any("broken" in w and "deliberate failure" in w for w in out.warnings)
    assert "broken" in out.leaderboard["unranked"]


def test_illegal_predictions_are_projected_onto_the_legal_space():
    def out_of_range(train, geometry, n_test):
        return np.full((n_test, geometry.positions), 999.0)

    out = run_research(_synthetic("loto7"), _cfg("loto7"),
                       predictors={"bad": out_of_range})
    row = next(r for r in out.leaderboard["rows"] if r["model_id"] == "bad")
    assert row["status"] == "SUCCEEDED"  # projected, not crashed
    assert row["point_estimate"] > 0


def test_theory_predictors_hit_their_exact_bounds():
    g = geometry_for("loto7")
    from loto.evaluation.theory_general import theoretical_bounds
    bounds = theoretical_bounds(g)
    pred = theory_median_predictor(pd.DataFrame(), g, 3)
    assert pred.shape == (3, 7)
    assert list(pred[0]) == list(bounds.median_prediction)


def test_frequency_predictor_requires_slot_columns():
    with pytest.raises(KeyError, match="slot columns"):
        frequency_predictor(pd.DataFrame({"x": [1, 2]}), geometry_for("loto7"), 1)


def test_impossible_fold_configuration_fails_loudly():
    with pytest.raises(ValueError, match="no folds constructible"):
        run_research(_synthetic("loto7", n=90), _cfg("loto7", min_train_size=200))


def test_config_validates_its_own_arguments():
    with pytest.raises(ValueError, match="horizon"):
        ResearchConfig(game="loto7", horizon=0)
    with pytest.raises(ValueError, match="alpha"):
        ResearchConfig(game="loto7", alpha=1.5)

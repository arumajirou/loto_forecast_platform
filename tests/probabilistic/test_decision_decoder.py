from __future__ import annotations

import numpy as np

from loto.game.geometry import geometry_for
from loto.probabilistic.decision import choose_points, hit1_utility
from loto.probabilistic.decoder import decode_select_positions


def test_hit1_utility_respects_digit_boundaries() -> None:
    probs = np.zeros((1, 10))
    probs[0, 0] = 0.6
    probs[0, 1] = 0.4
    utility = hit1_utility(probs)
    assert utility[0, 0] == 1.0
    assert utility[0, 1] == 1.0
    point = choose_points(probs, model_id="pp-posterior-utility-hit1", value_min=0)
    assert int(point[0]) in {0, 1}


def test_select_decoder_always_returns_legal_outcome() -> None:
    geometry = geometry_for("loto7")
    rng = np.random.default_rng(42)
    probabilities = rng.dirichlet(np.ones(geometry.universe_size), size=geometry.positions)
    decoded = decode_select_positions(probabilities, geometry)
    geometry.validate_outcome(decoded)

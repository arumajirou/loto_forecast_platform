import numpy as np

from loto.moirai2_campaign.geometry import geometry_for_game
from loto.moirai2_campaign.postprocess import constrained_integer_projection


def test_constrained_projection_is_in_range_unique_and_increasing() -> None:
    geometry = geometry_for_game("loto7")
    raw = np.asarray([11.449, 16.449, 21.449, 26.449, 31.449, 36.449, 41.449])
    projected = constrained_integer_projection(raw, geometry)
    assert projected.min() >= 1
    assert projected.max() <= 37
    assert len(set(projected.tolist())) == 7
    assert np.all(np.diff(projected) > 0)

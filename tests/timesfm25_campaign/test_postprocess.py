from __future__ import annotations

from loto.adapters.timesfm25.contracts import GameGeometry
from loto.timesfm25_campaign.postprocess import constrained_integer_projection


def test_constrained_projection_is_integer_unique_and_increasing() -> None:
    geometry = GameGeometry(
        game_id="loto7",
        position_count=7,
        candidate_min=1,
        candidate_max=37,
        strictly_increasing=True,
    )
    result = constrained_integer_projection([8.2, 8.1, 8.0, 7.9, 7.8, 40.0, -5.0], geometry)
    assert all(isinstance(value, int) for value in result)
    assert all(left < right for left, right in zip(result, result[1:], strict=False))
    assert result[0] >= 1 and result[-1] <= 37

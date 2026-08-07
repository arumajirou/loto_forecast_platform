from __future__ import annotations

import pytest
from pydantic import ValidationError

from loto.adapters.tabpfn_ts import GAME_GEOMETRIES, GameGeometry, geometry_for


def test_all_supported_game_geometries_are_explicit() -> None:
    assert set(GAME_GEOMETRIES) == {"numbers3", "numbers4", "miniloto", "loto6", "loto7"}
    assert geometry_for("numbers3").candidate_min == 0
    assert geometry_for("loto6").candidate_max == 43
    assert geometry_for("loto7").candidate_count == 37


def test_arbitrary_geometry_is_not_loto7_fixed() -> None:
    geometry = GameGeometry(
        game_id="custom",
        position_count=2,
        candidate_min=-2,
        candidate_max=8,
        selection_count=2,
        strictly_increasing=False,
    )
    assert geometry.candidate_count == 11
    assert geometry.validate_positions([-2, 8]) == (-2, 8)


def test_strict_geometry_rejects_unsorted_positions() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        geometry_for("miniloto").validate_positions([1, 2, 4, 4, 5])


def test_geometry_rejects_selection_position_mismatch() -> None:
    with pytest.raises(ValidationError, match="selection_count must equal position_count"):
        GameGeometry(
            game_id="bad",
            position_count=3,
            candidate_min=1,
            candidate_max=10,
            selection_count=2,
            strictly_increasing=True,
        )

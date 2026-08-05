from __future__ import annotations

import pytest

from loto.toto2_campaign.geometry import GAME_GEOMETRIES, GameGeometry, geometry_for_game


def test_geometry_inventory_is_exact() -> None:
    assert tuple(GAME_GEOMETRIES) == (
        "numbers3",
        "numbers4",
        "miniloto",
        "loto6",
        "loto7",
    )
    assert [geometry.position_count for geometry in GAME_GEOMETRIES.values()] == [3, 4, 5, 6, 7]


def test_unknown_geometry_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        geometry_for_game("unknown")


def test_invalid_strict_geometry_is_rejected() -> None:
    geometry = GameGeometry("invalid", 11, 0, 9, True)
    with pytest.raises(ValueError, match="more positions"):
        geometry.validate()

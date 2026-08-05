from __future__ import annotations

from loto.adapters.tirex2.contracts import GameGeometry

GAME_GEOMETRIES: dict[str, GameGeometry] = {
    "numbers3": GameGeometry(
        game_id="numbers3",
        position_count=3,
        candidate_min=0,
        candidate_max=9,
        strictly_increasing=False,
    ),
    "numbers4": GameGeometry(
        game_id="numbers4",
        position_count=4,
        candidate_min=0,
        candidate_max=9,
        strictly_increasing=False,
    ),
    "miniloto": GameGeometry(
        game_id="miniloto", position_count=5, candidate_min=1, candidate_max=31
    ),
    "loto6": GameGeometry(game_id="loto6", position_count=6, candidate_min=1, candidate_max=43),
    "loto7": GameGeometry(game_id="loto7", position_count=7, candidate_min=1, candidate_max=37),
}


def get_game_geometry(game_id: str) -> GameGeometry:
    try:
        return GAME_GEOMETRIES[game_id]
    except KeyError as exc:
        raise ValueError(f"unsupported game geometry: {game_id}") from exc

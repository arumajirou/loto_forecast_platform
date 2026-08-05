from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GameGeometry:
    game_id: str
    position_count: int
    candidate_min: int
    candidate_max: int
    strictly_increasing: bool

    def validate(self) -> None:
        if not self.game_id:
            raise ValueError("game_id must not be empty")
        if self.position_count < 1:
            raise ValueError("position_count must be positive")
        if self.candidate_min >= self.candidate_max:
            raise ValueError("candidate_min must be smaller than candidate_max")
        domain_size = self.candidate_max - self.candidate_min + 1
        if self.strictly_increasing and self.position_count > domain_size:
            raise ValueError("strict geometry has more positions than candidate values")


GAME_GEOMETRIES: dict[str, GameGeometry] = {
    "numbers3": GameGeometry("numbers3", 3, 0, 9, False),
    "numbers4": GameGeometry("numbers4", 4, 0, 9, False),
    "miniloto": GameGeometry("miniloto", 5, 1, 31, True),
    "loto6": GameGeometry("loto6", 6, 1, 43, True),
    "loto7": GameGeometry("loto7", 7, 1, 37, True),
}


def geometry_for_game(game_id: str) -> GameGeometry:
    try:
        geometry = GAME_GEOMETRIES[game_id]
    except KeyError as exc:
        raise ValueError(f"unsupported game geometry: {game_id}") from exc
    geometry.validate()
    return geometry

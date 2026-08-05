from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GameGeometry(BaseModel):
    """Game-independent output geometry for position and candidate formulations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: str = Field(min_length=1)
    position_count: int = Field(ge=1)
    candidate_min: int
    candidate_max: int
    selection_count: int = Field(ge=1)
    strictly_increasing: bool

    @property
    def candidate_count(self) -> int:
        return self.candidate_max - self.candidate_min + 1

    @model_validator(mode="after")
    def validate_geometry(self) -> GameGeometry:
        if self.candidate_max < self.candidate_min:
            raise ValueError("candidate_max must be >= candidate_min")
        if self.selection_count != self.position_count:
            raise ValueError("selection_count must equal position_count")
        if self.strictly_increasing and self.selection_count > self.candidate_count:
            raise ValueError("strictly increasing games cannot select more values than candidates")
        return self

    def validate_positions(self, values: Iterable[int]) -> tuple[int, ...]:
        positions = tuple(values)
        if len(positions) != self.position_count:
            raise ValueError(
                f"expected {self.position_count} positions, received {len(positions)}"
            )
        for value in positions:
            if not self.candidate_min <= value <= self.candidate_max:
                raise ValueError(
                    f"candidate {value} outside [{self.candidate_min}, {self.candidate_max}]"
                )
        if self.strictly_increasing and any(
            left >= right for left, right in zip(positions, positions[1:], strict=False)
        ):
            raise ValueError("positions must be strictly increasing")
        return positions


GAME_GEOMETRIES: dict[str, GameGeometry] = {
    "numbers3": GameGeometry(
        game_id="numbers3",
        position_count=3,
        candidate_min=0,
        candidate_max=9,
        selection_count=3,
        strictly_increasing=False,
    ),
    "numbers4": GameGeometry(
        game_id="numbers4",
        position_count=4,
        candidate_min=0,
        candidate_max=9,
        selection_count=4,
        strictly_increasing=False,
    ),
    "miniloto": GameGeometry(
        game_id="miniloto",
        position_count=5,
        candidate_min=1,
        candidate_max=31,
        selection_count=5,
        strictly_increasing=True,
    ),
    "loto6": GameGeometry(
        game_id="loto6",
        position_count=6,
        candidate_min=1,
        candidate_max=43,
        selection_count=6,
        strictly_increasing=True,
    ),
    "loto7": GameGeometry(
        game_id="loto7",
        position_count=7,
        candidate_min=1,
        candidate_max=37,
        selection_count=7,
        strictly_increasing=True,
    ),
}


def geometry_for(game_id: str) -> GameGeometry:
    try:
        return GAME_GEOMETRIES[game_id]
    except KeyError as exc:
        raise KeyError(f"unsupported game geometry: {game_id}") from exc

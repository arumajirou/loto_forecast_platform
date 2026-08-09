from __future__ import annotations

from dataclasses import dataclass

from loto.timer_base_84m_campaign._compat import StrEnum


class Game(StrEnum):
    NUMBERS3 = "numbers3"
    NUMBERS4 = "numbers4"
    MINILOTO = "miniloto"
    LOTO6 = "loto6"
    LOTO7 = "loto7"


@dataclass(frozen=True)
class GameGeometry:
    game: Game
    position_count: int
    draw_weekdays: tuple[int, ...]
    schedule_source: str


_SCHEDULE_SOURCE = "https://www.mizuhobank.co.jp/takarakuji/"
_GEOMETRIES: dict[Game, GameGeometry] = {
    Game.NUMBERS3: GameGeometry(Game.NUMBERS3, 3, (0, 1, 2, 3, 4), _SCHEDULE_SOURCE),
    Game.NUMBERS4: GameGeometry(Game.NUMBERS4, 4, (0, 1, 2, 3, 4), _SCHEDULE_SOURCE),
    Game.MINILOTO: GameGeometry(Game.MINILOTO, 5, (1,), _SCHEDULE_SOURCE),
    Game.LOTO6: GameGeometry(Game.LOTO6, 6, (0, 3), _SCHEDULE_SOURCE),
    Game.LOTO7: GameGeometry(Game.LOTO7, 7, (4,), _SCHEDULE_SOURCE),
}


def geometry_for(game: Game) -> GameGeometry:
    return _GEOMETRIES[game]

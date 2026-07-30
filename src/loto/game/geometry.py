"""Single source of truth for game geometry.

Constitution principle IV: no module outside ``loto.game`` may hard-code a universe size,
a draw size, or a digit count. Every such value flows from :class:`GameGeometry`.

Two families of Japanese lottery are modelled:

``select``  Draw ``k`` distinct numbers without replacement from ``1..n``
            (mini/loto6/loto7/bingo5). The natural target is either the ascending
            position vector (length ``k``) or the inclusion indicator over ``n`` numbers.

``digits``  Draw ``d`` independent digits from ``0..9`` with replacement
            (numbers3/numbers4). Leading zeros are significant. There is no
            "ascending" constraint and no inclusion vector over a large universe.

The two families need genuinely different metrics and decoders, so the geometry carries a
``family`` discriminator rather than pretending ``digits`` is a degenerate ``select``.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import comb
from typing import Literal

Family = Literal["select", "digits"]

__all__ = [
    "Family",
    "GameGeometry",
    "GEOMETRIES",
    "geometry_for",
    "geometry_from_spec",
    "known_games",
]


@dataclass(frozen=True)
class GameGeometry:
    """Immutable description of a game's combinatorial shape."""

    key: str
    family: Family
    positions: int
    """Number of predicted slots: ``k`` for select games, ``d`` for digit games."""
    value_min: int
    value_max: int
    bonus_count: int = 0
    display_name: str = ""
    draw_weekdays: tuple[int, ...] = ()

    # --- derived -----------------------------------------------------------------

    def __post_init__(self) -> None:
        if self.positions < 1:
            raise ValueError(f"{self.key}: positions must be >= 1")
        if self.value_max < self.value_min:
            raise ValueError(f"{self.key}: value_max must be >= value_min")
        if self.family == "select" and self.positions > self.universe_size:
            raise ValueError(f"{self.key}: cannot draw {self.positions} of {self.universe_size}")
        if self.family not in ("select", "digits"):
            raise ValueError(f"{self.key}: unknown family {self.family!r}")

    @property
    def universe_size(self) -> int:
        """Number of distinct values a single slot can take."""
        return self.value_max - self.value_min + 1

    @property
    def values(self) -> range:
        return range(self.value_min, self.value_max + 1)

    @property
    def n(self) -> int:
        """Alias used by combinatorial code: universe size for select games."""
        return self.universe_size

    @property
    def k(self) -> int:
        """Alias used by combinatorial code: draw size."""
        return self.positions

    @property
    def ascending(self) -> bool:
        """Whether slot values are constrained to be strictly increasing."""
        return self.family == "select"

    @property
    def distinct(self) -> bool:
        return self.family == "select"

    @property
    def outcome_space(self) -> int:
        """Total number of legal outcomes."""
        if self.family == "select":
            return comb(self.universe_size, self.positions)
        return self.universe_size**self.positions

    @property
    def inclusion_vector_length(self) -> int:
        """Length of the marginal-probability vector used by candidate models.

        For select games this is the universe size (``n`` numbers, each in/out).
        For digit games a single flat vector is meaningless, so we use the flattened
        ``positions x universe`` layout.
        """
        if self.family == "select":
            return self.universe_size
        return self.positions * self.universe_size

    @property
    def expected_inclusion_mass(self) -> float:
        """Sum the marginal inclusion vector must equal under a legal distribution."""
        return float(self.positions)

    def marginal_base_rate(self) -> float:
        """Probability a given value appears, under the uniform legal distribution."""
        if self.family == "select":
            return self.positions / self.universe_size
        return 1.0 / self.universe_size

    def validate_outcome(self, values: list[int] | tuple[int, ...]) -> None:
        """Raise ``ValueError`` when ``values`` is not a legal outcome for this game."""
        seq = list(values)
        if len(seq) != self.positions:
            raise ValueError(f"{self.key}: expected {self.positions} values, got {len(seq)}")
        for v in seq:
            if not (self.value_min <= v <= self.value_max):
                raise ValueError(
                    f"{self.key}: value {v} outside [{self.value_min}, {self.value_max}]"
                )
        if self.distinct and len(set(seq)) != len(seq):
            raise ValueError(f"{self.key}: values must be distinct")
        if self.ascending and any(a >= b for a, b in zip(seq, seq[1:])):
            raise ValueError(f"{self.key}: values must be strictly ascending")

    def is_legal(self, values: list[int] | tuple[int, ...]) -> bool:
        try:
            self.validate_outcome(values)
        except ValueError:
            return False
        return True

    def column_names(self) -> list[str]:
        prefix = "n" if self.family == "select" else "d"
        return [f"{prefix}{i}" for i in range(1, self.positions + 1)]

    def bonus_column_names(self) -> list[str]:
        return [f"bonus{i}" for i in range(1, self.bonus_count + 1)]

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "family": self.family,
            "positions": self.positions,
            "value_min": self.value_min,
            "value_max": self.value_max,
            "universe_size": self.universe_size,
            "bonus_count": self.bonus_count,
            "outcome_space": self.outcome_space,
        }


#: Canonical geometries for the six supported games.
GEOMETRIES: dict[str, GameGeometry] = {
    "mini": GameGeometry(
        key="mini", family="select", positions=5, value_min=1, value_max=31,
        bonus_count=1, display_name="ミニロト", draw_weekdays=(1,),
    ),
    "loto6": GameGeometry(
        key="loto6", family="select", positions=6, value_min=1, value_max=43,
        bonus_count=1, display_name="ロト6", draw_weekdays=(0, 3),
    ),
    "loto7": GameGeometry(
        key="loto7", family="select", positions=7, value_min=1, value_max=37,
        bonus_count=2, display_name="ロト7", draw_weekdays=(4,),
    ),
    "bingo5": GameGeometry(
        key="bingo5", family="select", positions=8, value_min=1, value_max=40,
        bonus_count=0, display_name="ビンゴ5", draw_weekdays=(2,),
    ),
    "numbers3": GameGeometry(
        key="numbers3", family="digits", positions=3, value_min=0, value_max=9,
        bonus_count=0, display_name="ナンバーズ3", draw_weekdays=(0, 1, 2, 3, 4),
    ),
    "numbers4": GameGeometry(
        key="numbers4", family="digits", positions=4, value_min=0, value_max=9,
        bonus_count=0, display_name="ナンバーズ4", draw_weekdays=(0, 1, 2, 3, 4),
    ),
}


def known_games() -> list[str]:
    return sorted(GEOMETRIES)


@lru_cache(maxsize=32)
def geometry_for(game: str) -> GameGeometry:
    try:
        return GEOMETRIES[game]
    except KeyError as exc:
        raise ValueError(f"unknown game={game!r}; available={known_games()}") from exc


def geometry_from_spec(spec: object) -> GameGeometry:
    """Build a geometry from a :class:`loto.data.lotteries.LotterySpec`-like object.

    Falls back to the canonical table when the key is known, so a config file that omits
    a field cannot silently produce a wrong universe size.
    """
    key = str(getattr(spec, "key", ""))
    if key in GEOMETRIES:
        return GEOMETRIES[key]
    kind = str(getattr(spec, "kind", "select"))
    family: Family = "digits" if kind.startswith("digit") else "select"
    if family == "digits":
        positions = int(getattr(spec, "digits_count", 0) or 0)
        return GameGeometry(
            key=key or "custom", family="digits", positions=positions,
            value_min=0, value_max=9,
            display_name=str(getattr(spec, "display_name", "")),
            draw_weekdays=tuple(getattr(spec, "draw_weekdays", ()) or ()),
        )
    positions = int(getattr(spec, "main_count", 0) or 0)
    return GameGeometry(
        key=key or "custom", family="select", positions=positions,
        value_min=int(getattr(spec, "number_min", 1)),
        value_max=int(getattr(spec, "number_max", 1)),
        bonus_count=int(getattr(spec, "bonus_count", 0) or 0),
        display_name=str(getattr(spec, "display_name", "")),
        draw_weekdays=tuple(getattr(spec, "draw_weekdays", ()) or ()),
    )

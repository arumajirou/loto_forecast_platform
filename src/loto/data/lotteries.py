from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LotterySpec:
    key: str
    display_name: str
    url: str
    kind: str
    main_count: int | None = None
    bonus_count: int = 0
    digits_count: int | None = None
    number_min: int = 1
    number_max: int = 37
    draw_weekdays: tuple[int, ...] = ()

    @property
    def candidate_numbers(self) -> range:
        return range(self.number_min, self.number_max + 1)


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[3] / "configs" / "lotteries.json"


def load_lottery_specs(path: str | Path | None = None) -> dict[str, LotterySpec]:
    config_path = Path(path) if path else default_config_path()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    return {
        key: LotterySpec(
            key=key,
            display_name=value["display_name"],
            url=value["url"],
            kind=value["kind"],
            main_count=value.get("main_count"),
            bonus_count=value.get("bonus_count", 0),
            digits_count=value.get("digits_count"),
            number_min=value.get("number_min", 1),
            number_max=value.get("number_max", 37),
            draw_weekdays=tuple(value.get("draw_weekdays", [])),
        )
        for key, value in raw.items()
    }


def get_lottery_spec(game: str, path: str | Path | None = None) -> LotterySpec:
    specs = load_lottery_specs(path)
    try:
        return specs[game]
    except KeyError as exc:
        raise ValueError(f"unknown game={game!r}; available={sorted(specs)}") from exc


def select_lottery_specs(
    games: str | list[str] | tuple[str, ...] | None,
    path: str | Path | None = None,
) -> list[LotterySpec]:
    """Resolve comma-separated game keys or ``all`` into ordered specs."""
    specs = load_lottery_specs(path)
    if games is None or games == "" or games == "all" or games == ["all"]:
        return list(specs.values())
    keys = (
        [item.strip() for item in games.split(",") if item.strip()]
        if isinstance(games, str)
        else [str(item).strip() for item in games if str(item).strip()]
    )
    unknown = [key for key in keys if key not in specs]
    if unknown:
        raise ValueError(f"unknown games={unknown!r}; available={sorted(specs)}")
    return [specs[key] for key in keys]

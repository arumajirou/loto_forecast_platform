"""Draw-aware scheduling plans and non-destructive run locks."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from loto.data.lineage import atomic_write_json
from loto.data.lotteries import get_lottery_spec, select_lottery_specs


@dataclass(frozen=True)
class SchedulePolicy:
    timezone: str = "Asia/Tokyo"
    run_hour: int = 20
    run_minute: int = 30
    delay_days: int = 0
    startup_cooldown_seconds: int = 900

    @classmethod
    def from_file(cls, path: str | Path | None = None) -> SchedulePolicy:
        if path is None:
            return cls()
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        section = raw.get("schedule", raw)
        return cls(**{key: section[key] for key in cls.__dataclass_fields__ if key in section})


@dataclass(frozen=True)
class ScheduledRun:
    game: str
    draw_weekday: int
    run_at: str
    timezone: str


def next_scheduled_run(
    game: str, *, now: datetime | None = None, policy: SchedulePolicy | None = None
) -> ScheduledRun:
    policy = policy or SchedulePolicy()
    tz = ZoneInfo(policy.timezone)
    current = now.astimezone(tz) if now is not None else datetime.now(tz)
    spec = get_lottery_spec(game)
    if not spec.draw_weekdays:
        raise ValueError(f"game has no draw weekdays: {game}")
    candidates: list[tuple[datetime, int]] = []
    for weekday in spec.draw_weekdays:
        delta = (weekday - current.weekday()) % 7
        date = (current + timedelta(days=delta + policy.delay_days)).date()
        candidate = datetime.combine(date, time(policy.run_hour, policy.run_minute), tzinfo=tz)
        if candidate <= current:
            candidate += timedelta(days=7)
        candidates.append((candidate, weekday))
    run_at, weekday = min(candidates, key=lambda item: item[0])
    return ScheduledRun(game, weekday, run_at.isoformat(), policy.timezone)


def build_schedule_plan(
    games: str | list[str] | None = "all",
    *,
    now: datetime | None = None,
    policy: SchedulePolicy | None = None,
) -> dict:
    policy = policy or SchedulePolicy()
    runs = [
        next_scheduled_run(spec.key, now=now, policy=policy) for spec in select_lottery_specs(games)
    ]
    return {
        "policy": asdict(policy),
        "runs": [asdict(item) for item in sorted(runs, key=lambda item: item.run_at)],
    }


class RunLock:
    """Cross-platform exclusive lock based on atomic file creation."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.fd: int | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(
                self.fd,
                json.dumps(
                    {"pid": os.getpid(), "created_at": datetime.now().astimezone().isoformat()}
                ).encode(),
            )
        except FileExistsError as exc:
            raise RuntimeError(f"another scheduled run appears active: {self.path}") from exc

    def release(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.path.unlink(missing_ok=True)

    def __enter__(self) -> RunLock:
        self.acquire()
        return self

    def __exit__(self, *_exc) -> None:
        self.release()


def write_schedule_plan(plan: dict, path: str | Path) -> Path:
    return atomic_write_json(path, plan)

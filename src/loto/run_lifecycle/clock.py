"""Injected clocks used by lifecycle and lease logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Clock interface. Core services never call wall-clock APIs directly."""

    def now(self) -> datetime:
        """Return a timezone-aware UTC timestamp."""


@dataclass(frozen=True, slots=True)
class SystemClock:
    """Production clock adapter. It is injected at the application boundary."""

    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(slots=True)
class ManualClock:
    """Deterministic mutable clock for tests and replay simulations."""

    current: datetime

    def __post_init__(self) -> None:
        self._validate(self.current)

    @staticmethod
    def _validate(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("ManualClock requires a timezone-aware UTC datetime")

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> datetime:
        if delta.total_seconds() < 0:
            raise ValueError("ManualClock cannot move backwards")
        self.current += delta
        return self.current

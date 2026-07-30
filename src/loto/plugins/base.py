from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class LotterySpec:
    name: str
    max_number: int
    picks: int
    draw_interval_days: int = 7

    def validate_numbers(self, numbers: list[int]) -> None:
        if len(numbers) != self.picks:
            raise ValueError(f"expected {self.picks} numbers")
        if any(n < 1 or n > self.max_number for n in numbers):
            raise ValueError("number outside legal range")
        if any(a >= b for a, b in zip(numbers, numbers[1:])):
            raise ValueError("numbers must be strictly ascending")


LOTO7 = LotterySpec(name="loto7", max_number=37, picks=7, draw_interval_days=7)

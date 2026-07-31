from __future__ import annotations

from dataclasses import asdict, dataclass
from fractions import Fraction
from math import comb


@dataclass(frozen=True)
class LotterySpec:
    n: int
    k: int
    tau: int = 1

    @property
    def total(self) -> int:
        return comb(self.n, self.k)


def position_pmf(spec: LotterySpec) -> dict[int, dict[int, Fraction]]:
    out = {}
    for pos in range(1, spec.k + 1):
        row = {
            v: Fraction(comb(v - 1, pos - 1) * comb(spec.n - v, spec.k - pos), spec.total)
            for v in range(1, spec.n + 1)
        }
        if sum(row.values()) != 1:
            raise AssertionError("PMF not normalized")
        out[pos] = row
    return out


def _window(row, center, tau):
    return sum(row.get(v, Fraction(0)) for v in range(center - tau, center + tau + 1))


def _mae(row, center, n):
    return sum(row[v] * abs(v - center) for v in range(1, n + 1))


def solve_within_tau_optimum(spec: LotterySpec) -> dict:
    pmf = position_pmf(spec)
    predictions = {"opt": [], "median": [], "meanround": []}
    positions = []
    totals = {
        "opt_tau": Fraction(0),
        "median_tau": Fraction(0),
        "opt_mae": Fraction(0),
        "median_mae": Fraction(0),
    }
    for pos in range(1, spec.k + 1):
        row = pmf[pos]
        cumulative = Fraction(0)
        median = None
        mean = sum(row[v] * v for v in range(1, spec.n + 1))
        for v in range(1, spec.n + 1):
            cumulative += row[v]
            if median is None and cumulative >= Fraction(1, 2):
                median = v
        opt = min(
            range(1, spec.n + 1),
            key=lambda c: (-_window(row, c, spec.tau), _mae(row, c, spec.n), c),
        )
        meanround = int(mean + Fraction(1, 2))
        predictions["opt"].append(opt)
        predictions["median"].append(median)
        predictions["meanround"].append(meanround)
        totals["opt_tau"] += _window(row, opt, spec.tau)
        totals["median_tau"] += _window(row, median, spec.tau)
        totals["opt_mae"] += _mae(row, opt, spec.n)
        totals["median_mae"] += _mae(row, median, spec.n)
        positions.append({"position": pos, "opt": opt, "median": median, "mean": float(mean)})
    return {
        "spec": asdict(spec),
        "positions": positions,
        "predictions": predictions,
        "summary": {k: float(v / spec.k) for k, v in totals.items()},
        "legal_ascending": {
            k: all(a < b for a, b in zip(vals, vals[1:], strict=False))
            for k, vals in predictions.items()
        },
    }

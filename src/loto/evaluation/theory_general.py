"""Exact theoretical bounds for every supported game.

For ``select`` games the ``p``-th smallest of ``k`` values drawn without replacement from
``1..n`` has the negative-hypergeometric (order-statistic) pmf

    P(V_p = v) = C(v-1, p-1) * C(n-v, k-p) / C(n, k)

which is exact in :class:`fractions.Fraction` arithmetic. For ``digits`` games each slot is
independent uniform on ``0..9``, so the pmf is flat and every bound is closed-form.

Three bounds are reported per game because they are *not* simultaneously attainable:

``median``   minimises expected absolute error per slot (the MAE floor)
``mean``     minimises expected squared error per slot (the MSE floor)
``tau``      maximises P(|prediction - actual| <= tau) per slot (the hit-rate ceiling)

Reporting only one of these is how a platform ends up claiming a model "beat the floor".
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import comb

from loto.game.geometry import GameGeometry, geometry_for

__all__ = [
    "TheoryBounds",
    "position_pmf",
    "theoretical_bounds",
    "bounds_table",
]


def position_pmf(geometry: GameGeometry) -> dict[int, dict[int, Fraction]]:
    """Exact per-slot pmf. Keys are 1-based slots; inner keys are game values."""
    if geometry.family == "digits":
        uniform = Fraction(1, geometry.universe_size)
        return {
            slot: {v: uniform for v in geometry.values}
            for slot in range(1, geometry.positions + 1)
        }

    n, k = geometry.universe_size, geometry.positions
    total = comb(n, k)
    offset = geometry.value_min - 1  # map values back onto 1..n
    out: dict[int, dict[int, Fraction]] = {}
    for slot in range(1, k + 1):
        row = {
            v + offset: Fraction(comb(v - 1, slot - 1) * comb(n - v, k - slot), total)
            for v in range(1, n + 1)
        }
        if sum(row.values()) != 1:
            raise AssertionError(f"{geometry.key} slot {slot}: pmf not normalised")
        out[slot] = row
    return out


def _mae(row: dict[int, Fraction], center: int) -> Fraction:
    return sum(p * abs(v - center) for v, p in row.items())


def _mse(row: dict[int, Fraction], center: int) -> Fraction:
    return sum(p * (v - center) ** 2 for v, p in row.items())


def _window(row: dict[int, Fraction], center: int, tau: int) -> Fraction:
    return sum(row.get(v, Fraction(0)) for v in range(center - tau, center + tau + 1))


@dataclass(frozen=True)
class TheoryBounds:
    """Attainable-by-construction bounds for one game at one tolerance."""

    game: str
    family: str
    positions: int
    universe_size: int
    outcome_space: int
    tau: int
    mae_floor: float
    """Minimum achievable mean absolute error per slot (median predictor)."""
    mse_floor: float
    """Minimum achievable mean squared error per slot (mean predictor)."""
    within_tau_ceiling: float
    """Maximum achievable P(|err| <= tau) per slot (modal-window predictor)."""
    median_prediction: tuple[int, ...]
    mean_prediction: tuple[int, ...]
    tau_prediction: tuple[int, ...]
    median_within_tau: float
    """Within-tau rate of the MAE-optimal predictor -- strictly <= the ceiling."""
    tau_mae: float
    """MAE of the hit-rate-optimal predictor -- strictly >= the floor."""
    expected_hits: float
    """Expected set-overlap of any legal guess with the drawn set (select only)."""
    legal_median: bool
    legal_tau: bool
    single_ticket_probability: float

    def to_dict(self) -> dict[str, object]:
        return {
            "game": self.game,
            "family": self.family,
            "positions": self.positions,
            "universe_size": self.universe_size,
            "outcome_space": self.outcome_space,
            "tau": self.tau,
            "mae_floor": self.mae_floor,
            "mse_floor": self.mse_floor,
            "within_tau_ceiling": self.within_tau_ceiling,
            "median_prediction": list(self.median_prediction),
            "mean_prediction": list(self.mean_prediction),
            "tau_prediction": list(self.tau_prediction),
            "median_within_tau": self.median_within_tau,
            "tau_mae": self.tau_mae,
            "expected_hits": self.expected_hits,
            "legal_median": self.legal_median,
            "legal_tau": self.legal_tau,
            "single_ticket_probability": self.single_ticket_probability,
        }


def theoretical_bounds(game: str | GameGeometry, tau: int = 1) -> TheoryBounds:
    geometry = game if isinstance(game, GameGeometry) else geometry_for(game)
    if tau < 0:
        raise ValueError("tau must be >= 0")
    pmf = position_pmf(geometry)

    med: list[int] = []
    mean_pred: list[int] = []
    tau_pred: list[int] = []
    tot_mae = Fraction(0)
    tot_mse = Fraction(0)
    tot_tau = Fraction(0)
    tot_med_tau = Fraction(0)
    tot_tau_mae = Fraction(0)

    for slot in range(1, geometry.positions + 1):
        row = pmf[slot]
        values = sorted(row)

        cumulative = Fraction(0)
        median = values[-1]
        for v in values:
            cumulative += row[v]
            if cumulative >= Fraction(1, 2):
                median = v
                break
        mean = sum(row[v] * v for v in values)
        # integer minimiser of squared error is the rounded mean
        mean_int = min(values, key=lambda c: (_mse(row, c), c))
        # tie-break: maximise window, then minimise MAE, then smallest value
        best_tau = min(values, key=lambda c: (-_window(row, c, tau), _mae(row, c), c))

        med.append(median)
        mean_pred.append(mean_int)
        tau_pred.append(best_tau)
        tot_mae += _mae(row, median)
        tot_mse += _mse(row, mean_int)
        tot_tau += _window(row, best_tau, tau)
        tot_med_tau += _window(row, median, tau)
        tot_tau_mae += _mae(row, best_tau)
        del mean  # exact mean retained only for documentation

    kf = geometry.positions
    expected_hits = (
        geometry.positions**2 / geometry.universe_size
        if geometry.family == "select"
        else geometry.positions / geometry.universe_size
    )
    return TheoryBounds(
        game=geometry.key,
        family=geometry.family,
        positions=geometry.positions,
        universe_size=geometry.universe_size,
        outcome_space=geometry.outcome_space,
        tau=tau,
        mae_floor=float(tot_mae / kf),
        mse_floor=float(tot_mse / kf),
        within_tau_ceiling=float(tot_tau / kf),
        median_prediction=tuple(med),
        mean_prediction=tuple(mean_pred),
        tau_prediction=tuple(tau_pred),
        median_within_tau=float(tot_med_tau / kf),
        tau_mae=float(tot_tau_mae / kf),
        expected_hits=float(expected_hits),
        legal_median=geometry.is_legal(med),
        legal_tau=geometry.is_legal(tau_pred),
        single_ticket_probability=1.0 / geometry.outcome_space,
    )


def bounds_table(tau: int = 1) -> list[dict[str, object]]:
    """Bounds for every known game, ordered by key. Used to regenerate documentation."""
    from loto.game.geometry import known_games

    return [theoretical_bounds(g, tau=tau).to_dict() for g in known_games()]

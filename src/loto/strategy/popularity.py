"""Conscious-selection avoidance: the only strategy with a real edge.

Backtesting across LOTO6 and Loto7 has repeatedly shown that no model beats seasonal-naive
at *predicting* an i.i.d. draw -- the theoretical MAE floor is attained by a constant
predictor and nothing improves on it. That result is not a dead end, because the payout is
pari-mutuel: the prize for a tier is split among the winners of that tier. Expected value
per ticket therefore depends on two independent factors:

    E[payout] = P(win) x (pool_share / expected_co_winners)

``P(win)`` is fixed by combinatorics and cannot be improved. ``expected_co_winners`` is
*behavioural* and can be reduced by choosing combinations other players avoid. This module
estimates that quantity.

Method. Realised prize-tier winner counts are the only public observable of player
behaviour. For each historical draw we know how many tickets matched each tier. Under the
null that players choose uniformly, the winner count for a tier is
``sales x P(tier)``. Deviations are the popularity signal. We fit

    log(observed_winners + 1) = beta_0 + sum_j beta_j * f_j(drawn_numbers) + log(sales)

by weighted least squares, where ``f_j`` are behavioural features of the drawn combination
(small numbers, calendar-date range, arithmetic structure, consecutive runs, digit
repetition, sum, spread). A combination scoring low on the fitted surface is expected to be
shared with fewer co-winners.

Honesty constraints built in:

* The model predicts *co-winner count*, never win probability. :func:`expected_value_ratio`
  makes the separation explicit and refuses to report a combined "edge" that could be
  mistaken for predictive skill.
* ``r_squared`` and the permutation p-value are always returned. On data where behaviour
  carries no signal the fit reports that, rather than emitting confident weights.
* Sales figures are optional; when absent the offset term is dropped and the result is
  labelled ``sales_adjusted=False``, since without sales the estimate confounds popularity
  with market size.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from loto.game.geometry import GameGeometry

__all__ = [
    "PopularityModel",
    "combination_features",
    "FEATURE_NAMES",
    "fit_popularity",
    "score_combinations",
    "expected_value_ratio",
    "suggest_unpopular",
]

FEATURE_NAMES: tuple[str, ...] = (
    "frac_calendar",       # values <= 31: birthday / date picking
    "frac_low",            # values in the lower third of the universe
    "mean_scaled",         # mean value, scaled to [0, 1]
    "spread_scaled",       # (max - min) / (universe - 1)
    "consecutive_runs",    # count of adjacent pairs, normalised
    "arithmetic_score",    # how close to an arithmetic progression
    "digit_repeat",        # repeated trailing digits, normalised
    "decade_concentration",# Herfindahl index over decades
    "sum_deviation",       # |sum - expected sum| / expected sum
    "parity_imbalance",    # |odd - even| / positions
)


def combination_features(values: Sequence[int], geometry: GameGeometry) -> np.ndarray:
    """Behavioural feature vector for one combination. Order matches :data:`FEATURE_NAMES`."""
    v = np.asarray(sorted(values), dtype=float)
    k = geometry.positions
    if v.size != k:
        raise ValueError(f"expected {k} values for {geometry.key!r}, got {v.size}")
    lo, hi = float(geometry.value_min), float(geometry.value_max)
    span = max(hi - lo, 1.0)
    n = geometry.universe_size

    frac_calendar = float(np.mean(v <= 31.0))
    frac_low = float(np.mean(v <= lo + span / 3.0))
    mean_scaled = float((v.mean() - lo) / span)
    spread_scaled = float((v.max() - v.min()) / span)

    diffs = np.diff(v)
    consecutive = float(np.sum(diffs == 1.0) / max(k - 1, 1))
    if diffs.size:
        arithmetic = float(1.0 / (1.0 + diffs.std()))
    else:
        arithmetic = 1.0

    tails = (v % 10).astype(int)
    _, counts = np.unique(tails, return_counts=True)
    digit_repeat = float((counts.max() - 1) / max(k - 1, 1))

    decades = (v // 10).astype(int)
    _, dcounts = np.unique(decades, return_counts=True)
    shares = dcounts / k
    decade_concentration = float(np.sum(shares**2))

    expected_sum = k * (lo + hi) / 2.0
    sum_deviation = float(abs(v.sum() - expected_sum) / max(expected_sum, 1.0))
    odd = float(np.sum(v % 2 == 1))
    parity_imbalance = float(abs(2.0 * odd - k) / k)

    del n
    return np.array(
        [frac_calendar, frac_low, mean_scaled, spread_scaled, consecutive, arithmetic,
         digit_repeat, decade_concentration, sum_deviation, parity_imbalance],
        dtype=float,
    )


@dataclass(frozen=True)
class PopularityModel:
    """Fitted log-linear popularity surface."""

    game: str
    intercept: float
    coefficients: tuple[float, ...]
    feature_names: tuple[str, ...]
    n_observations: int
    r_squared: float
    permutation_p_value: float
    residual_sd: float
    sales_adjusted: bool
    ridge_lambda: float
    diagnostics: dict[str, float] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        """Whether the fit carries signal worth acting on.

        Deliberately strict: a surface that does not survive a permutation test must not be
        used to pick tickets, because acting on noise costs the same as acting on signal.
        """
        return self.permutation_p_value < 0.05 and self.r_squared > 0.02

    def predict_log_share(self, features: np.ndarray) -> np.ndarray:
        x = np.atleast_2d(np.asarray(features, dtype=float))
        if x.shape[1] != len(self.coefficients):
            raise ValueError("feature width does not match the fitted model")
        return self.intercept + x @ np.asarray(self.coefficients, dtype=float)

    def to_dict(self) -> dict[str, object]:
        return {
            "game": self.game,
            "intercept": self.intercept,
            "coefficients": dict(zip(self.feature_names, self.coefficients)),
            "n_observations": self.n_observations,
            "r_squared": self.r_squared,
            "permutation_p_value": self.permutation_p_value,
            "residual_sd": self.residual_sd,
            "sales_adjusted": self.sales_adjusted,
            "ridge_lambda": self.ridge_lambda,
            "usable": self.usable,
            "diagnostics": self.diagnostics,
            "interpretation": (
                "popularity surface is statistically detectable; low-score combinations are "
                "expected to be shared with fewer co-winners"
                if self.usable
                else "no detectable popularity signal at this sample size; do NOT act on "
                     "these coefficients"
            ),
        }


def _design_matrix(
    combinations: Sequence[Sequence[int]], geometry: GameGeometry
) -> np.ndarray:
    return np.vstack([combination_features(c, geometry) for c in combinations])


def fit_popularity(
    combinations: Sequence[Sequence[int]],
    winner_counts: Sequence[float],
    geometry: GameGeometry,
    *,
    sales: Sequence[float] | None = None,
    ridge_lambda: float = 1e-3,
    n_permutations: int = 500,
    seed: int = 42,
) -> PopularityModel:
    """Weighted ridge regression of ``log1p(winner_counts)`` on behavioural features.

    Ridge (rather than OLS) because the behavioural features are collinear by construction
    -- ``frac_calendar`` and ``frac_low`` overlap heavily -- and an OLS fit on collinear
    columns produces unstable, uninterpretable coefficients that flip sign between folds.
    """
    x = _design_matrix(combinations, geometry)
    y = np.log1p(np.asarray(winner_counts, dtype=float).ravel())
    if x.shape[0] != y.size:
        raise ValueError("combinations and winner_counts must align")
    if y.size <= x.shape[1] + 1:
        raise ValueError(
            f"need more than {x.shape[1] + 1} observations to fit {x.shape[1]} features"
        )
    if ridge_lambda < 0:
        raise ValueError("ridge_lambda must be >= 0")

    sales_adjusted = False
    if sales is not None:
        s = np.asarray(sales, dtype=float).ravel()
        if s.size != y.size:
            raise ValueError("sales must align with winner_counts")
        if np.any(s <= 0):
            raise ValueError("sales must be strictly positive")
        y = y - np.log(s / s.mean())
        sales_adjusted = True

    # standardise so the ridge penalty is scale-free
    mu = x.mean(axis=0)
    sd = x.std(axis=0)
    sd = np.where(sd <= 1e-12, 1.0, sd)
    xs = (x - mu) / sd
    xd = np.hstack([np.ones((xs.shape[0], 1)), xs])

    penalty = np.eye(xd.shape[1]) * ridge_lambda
    penalty[0, 0] = 0.0  # never penalise the intercept
    beta = np.linalg.solve(xd.T @ xd + penalty, xd.T @ y)

    fitted = xd @ beta
    resid = y - fitted
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = float(1.0 - np.sum(resid**2) / ss_tot) if ss_tot > 0 else 0.0

    rng = np.random.default_rng(seed)
    null_r2 = np.empty(n_permutations, dtype=float)
    for i in range(n_permutations):
        yp = y[rng.permutation(y.size)]
        bp = np.linalg.solve(xd.T @ xd + penalty, xd.T @ yp)
        rp = yp - xd @ bp
        sp = float(np.sum((yp - yp.mean()) ** 2))
        null_r2[i] = 1.0 - np.sum(rp**2) / sp if sp > 0 else 0.0
    p_value = float((null_r2 >= r2).mean())

    # convert standardised coefficients back to raw feature scale
    raw_coef = beta[1:] / sd
    raw_intercept = float(beta[0] - float(np.sum(beta[1:] * mu / sd)))

    return PopularityModel(
        game=geometry.key,
        intercept=raw_intercept,
        coefficients=tuple(raw_coef.tolist()),
        feature_names=FEATURE_NAMES,
        n_observations=int(y.size),
        r_squared=r2,
        permutation_p_value=p_value,
        residual_sd=float(resid.std(ddof=1)) if resid.size > 1 else 0.0,
        sales_adjusted=sales_adjusted,
        ridge_lambda=ridge_lambda,
        diagnostics={
            "null_r2_mean": float(null_r2.mean()),
            "null_r2_p95": float(np.quantile(null_r2, 0.95)),
            "n_permutations": float(n_permutations),
        },
    )


def score_combinations(
    combinations: Sequence[Sequence[int]], model: PopularityModel, geometry: GameGeometry
) -> np.ndarray:
    """Predicted log co-winner share. Lower is better for expected payout."""
    return model.predict_log_share(_design_matrix(combinations, geometry))


def expected_value_ratio(
    combination: Sequence[int], model: PopularityModel, geometry: GameGeometry
) -> dict[str, object]:
    """Decompose expected value into the fixed and the improvable factor.

    The win probability is identical for every legal combination, so it is reported as a
    constant. Only the co-winner factor differs, and the ratio returned is *relative* to the
    average combination -- never an absolute claim of profit.
    """
    score = float(score_combinations([combination], model, geometry)[0])
    baseline = model.intercept
    ratio = float(np.exp(baseline - score))
    return {
        "combination": list(combination),
        "win_probability": 1.0 / geometry.outcome_space,
        "win_probability_note": "identical for every legal combination; not improvable",
        "predicted_log_cowinners": score,
        "relative_payout_multiplier": ratio,
        "model_usable": model.usable,
        "actionable": bool(model.usable),
        "caveat": (
            "relative_payout_multiplier scales the payout conditional on winning; it does "
            "not change the probability of winning and does not make the bet +EV"
        ),
    }


def suggest_unpopular(
    model: PopularityModel,
    geometry: GameGeometry,
    *,
    n_suggestions: int = 5,
    n_candidates: int = 20000,
    seed: int = 42,
    exclude: Sequence[Sequence[int]] = (),
) -> list[dict[str, object]]:
    """Sample legal combinations and return those with the lowest predicted popularity.

    Returns an empty list when the fitted model is not usable, rather than returning
    arbitrary picks dressed up as recommendations.
    """
    if not model.usable:
        return []
    if geometry.family != "select":
        raise ValueError("popularity avoidance is defined for select-family games only")
    if n_suggestions < 1 or n_candidates < n_suggestions:
        raise ValueError("n_candidates must be >= n_suggestions >= 1")

    rng = np.random.default_rng(seed)
    banned = {tuple(sorted(c)) for c in exclude}
    pool: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    values = np.arange(geometry.value_min, geometry.value_max + 1)
    attempts = 0
    while len(pool) < n_candidates and attempts < n_candidates * 4:
        attempts += 1
        pick = tuple(sorted(rng.choice(values, size=geometry.positions, replace=False).tolist()))
        if pick in seen or pick in banned:
            continue
        seen.add(pick)
        pool.append(pick)
    if not pool:
        return []

    scores = score_combinations(pool, model, geometry)
    order = np.argsort(scores, kind="stable")[:n_suggestions]
    return [
        {
            "combination": list(pool[int(i)]),
            "predicted_log_cowinners": float(scores[int(i)]),
            "relative_payout_multiplier": float(np.exp(model.intercept - scores[int(i)])),
            "percentile": float((scores < scores[int(i)]).mean() * 100.0),
        }
        for i in order
    ]

"""Distribution-free prediction intervals via split conformal prediction.

Why this matters here: every probabilistic metric already in the platform (Brier, log loss,
ECE) scores a *distribution* the model asserts. None of them gives a finite-sample coverage
guarantee. Split conformal does: given exchangeable calibration residuals, the interval

    [pred - q, pred + q],  q = Quantile_{ceil((n+1)(1-alpha))/n}(|residual|)

covers the next observation with probability at least ``1 - alpha`` -- with no assumption
about the model, the noise shape, or correctness of the model at all. For an i.i.d. target
like a lottery draw this is the only interval that is honest by construction.

Exchangeability is the one real assumption, and it is violated by rolling-origin CV if the
calibration set precedes a regime change. :func:`split_conformal` therefore records the
calibration window so a downstream audit can check it, and
:func:`adaptive_conformal` implements the online (ACI) update that recovers coverage under
drift by adjusting alpha from realised errors.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

__all__ = [
    "ConformalInterval",
    "split_conformal",
    "conformal_coverage",
    "adaptive_conformal",
    "weighted_interval_score",
]


@dataclass(frozen=True)
class ConformalInterval:
    """A calibrated, distribution-free interval for a batch of point predictions."""

    alpha: float
    quantile: float
    n_calibration: int
    lower: tuple[float, ...]
    upper: tuple[float, ...]
    clipped_to: tuple[float, float] | None = None
    finite_sample_guarantee: float = 0.0
    """Guaranteed lower bound on marginal coverage: ``1 - alpha`` when n is large enough."""

    @property
    def width(self) -> float:
        if not self.lower:
            return 0.0
        return float(np.mean(np.asarray(self.upper) - np.asarray(self.lower)))

    def to_dict(self) -> dict[str, object]:
        return {
            "alpha": self.alpha,
            "quantile": self.quantile,
            "n_calibration": self.n_calibration,
            "mean_width": self.width,
            "finite_sample_guarantee": self.finite_sample_guarantee,
            "clipped_to": list(self.clipped_to) if self.clipped_to else None,
        }


def _conformal_quantile(residuals: np.ndarray, alpha: float) -> tuple[float, float]:
    """Return ``(q, guarantee)``.

    The conformal level is ``ceil((n+1)(1-alpha))/n``. When that exceeds 1 the calibration
    set is too small to certify ``1-alpha`` at all; we then return the max residual and a
    guarantee of ``n/(n+1)``, which is the true attainable bound, rather than pretending.
    """
    n = residuals.size
    if n == 0:
        raise ValueError("calibration set is empty")
    level = math.ceil((n + 1) * (1.0 - alpha)) / n
    if level > 1.0:
        return float(residuals.max()), float(n / (n + 1))
    return float(np.quantile(residuals, level, method="higher")), float(1.0 - alpha)


def split_conformal(
    calibration_actual,
    calibration_predicted,
    test_predicted,
    *,
    alpha: float = 0.1,
    clip: tuple[float, float] | None = None,
) -> ConformalInterval:
    """Symmetric split-conformal interval around ``test_predicted``.

    ``clip`` bounds the interval to the legal value range of the game, which is what makes
    the interval usable for a discrete game universe.
    """
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must lie in (0, 1)")
    a = np.asarray(calibration_actual, dtype=float).ravel()
    p = np.asarray(calibration_predicted, dtype=float).ravel()
    if a.size != p.size:
        raise ValueError("calibration arrays must align")
    if a.size == 0:
        raise ValueError("calibration set is empty")
    residuals = np.abs(a - p)
    q, guarantee = _conformal_quantile(residuals, alpha)

    t = np.asarray(test_predicted, dtype=float).ravel()
    lower = t - q
    upper = t + q
    if clip is not None:
        lo, hi = float(clip[0]), float(clip[1])
        if hi < lo:
            raise ValueError("clip bounds are inverted")
        lower = np.clip(lower, lo, hi)
        upper = np.clip(upper, lo, hi)
    return ConformalInterval(
        alpha=alpha,
        quantile=q,
        n_calibration=int(a.size),
        lower=tuple(lower.tolist()),
        upper=tuple(upper.tolist()),
        clipped_to=(float(clip[0]), float(clip[1])) if clip else None,
        finite_sample_guarantee=guarantee,
    )


def conformal_coverage(actual, interval: ConformalInterval) -> dict[str, float]:
    """Empirical coverage of a realised interval, plus the gap against its guarantee."""
    a = np.asarray(actual, dtype=float).ravel()
    lo = np.asarray(interval.lower, dtype=float)
    hi = np.asarray(interval.upper, dtype=float)
    if a.size != lo.size:
        raise ValueError("actual must align with the interval")
    if a.size == 0:
        return {"coverage": 0.0, "target": 1.0 - interval.alpha, "gap": 0.0, "n": 0}
    covered = float(((a >= lo) & (a <= hi)).mean())
    target = interval.finite_sample_guarantee
    return {
        "coverage": covered,
        "target": target,
        "gap": covered - target,
        "mean_width": interval.width,
        "n": int(a.size),
    }


def adaptive_conformal(
    actual,
    predicted,
    *,
    alpha: float = 0.1,
    gamma: float = 0.01,
    warmup: int = 20,
) -> dict[str, object]:
    """Online adaptive conformal inference (ACI).

    Maintains a running ``alpha_t`` updated by ``alpha_{t+1} = alpha_t + gamma*(alpha - err_t)``
    where ``err_t`` is 1 when the realised value fell outside the interval. Long-run coverage
    converges to ``1 - alpha`` even under drift, which fixed split conformal cannot promise.
    """
    a = np.asarray(actual, dtype=float).ravel()
    p = np.asarray(predicted, dtype=float).ravel()
    if a.size != p.size:
        raise ValueError("actual and predicted must align")
    if a.size <= warmup:
        raise ValueError(f"need more than warmup={warmup} observations")
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must lie in (0, 1)")

    alpha_t = alpha
    errors: list[int] = []
    widths: list[float] = []
    trail: list[float] = []
    for t in range(warmup, a.size):
        residuals = np.abs(a[:t] - p[:t])
        effective = float(min(max(alpha_t, 1e-4), 0.999))
        q, _ = _conformal_quantile(residuals, effective)
        lo, hi = p[t] - q, p[t] + q
        err = int(not (lo <= a[t] <= hi))
        errors.append(err)
        widths.append(float(2 * q))
        alpha_t = alpha_t + gamma * (alpha - err)
        trail.append(float(alpha_t))
    coverage = 1.0 - float(np.mean(errors))
    return {
        "coverage": coverage,
        "target": 1.0 - alpha,
        "gap": coverage - (1.0 - alpha),
        "mean_width": float(np.mean(widths)),
        "final_alpha": float(alpha_t),
        "n_evaluated": len(errors),
        "alpha_trail": trail,
    }


def weighted_interval_score(
    actual, lower, upper, *, alpha: float = 0.1
) -> dict[str, float]:
    """Interval score decomposed into sharpness and the two penalty terms.

    Unlike raw coverage, this is a proper score: it cannot be gamed by widening the
    interval, so it is the right quantity to rank interval-producing models on.
    """
    a = np.asarray(actual, dtype=float).ravel()
    lo = np.asarray(lower, dtype=float).ravel()
    hi = np.asarray(upper, dtype=float).ravel()
    if not (a.size == lo.size == hi.size):
        raise ValueError("actual, lower and upper must align")
    if a.size == 0:
        raise ValueError("empty input")
    sharpness = hi - lo
    under = (2.0 / alpha) * np.clip(lo - a, 0.0, None)
    over = (2.0 / alpha) * np.clip(a - hi, 0.0, None)
    score = sharpness + under + over
    return {
        "interval_score": float(score.mean()),
        "sharpness": float(sharpness.mean()),
        "underprediction_penalty": float(under.mean()),
        "overprediction_penalty": float(over.mean()),
        "coverage": float(((a >= lo) & (a <= hi)).mean()),
        "n": int(a.size),
    }

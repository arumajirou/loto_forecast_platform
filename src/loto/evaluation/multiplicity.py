"""Multiple-comparison control for model leaderboards.

Sweeping 100+ models against a baseline and reporting the winner's raw p-value is the
single most common way a noise-only dataset produces a "significant" result. With 100
independent tests at alpha=0.05 the probability of at least one false positive is
1 - 0.95^100 = 99.4%.

Three procedures are provided:

``holm``          Step-down Bonferroni. Controls family-wise error rate (FWER) under
                  arbitrary dependence. Conservative but assumption-free.
``benjamini_hochberg``
                  Step-up. Controls false discovery rate (FDR) under independence or
                  positive regression dependence. More power, weaker guarantee.
``romano_wolf``   Bootstrap step-down on the studentised statistics. Controls FWER while
                  exploiting the *actual* correlation between models, which for a model
                  sweep is very high (all models see the same folds). Usually far more
                  powerful than Holm at the same guarantee.

Also provided is :func:`paired_bootstrap_p` -- a paired, two-sided bootstrap p-value for
the difference between a candidate and the baseline on the same draws, which is the correct
pairing for a rolling-CV sweep.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "Correction",
    "holm",
    "benjamini_hochberg",
    "romano_wolf",
    "paired_bootstrap_p",
    "correct",
    "family_wise_false_positive_probability",
]

_METHODS = ("holm", "benjamini_hochberg", "romano_wolf", "none")


@dataclass(frozen=True)
class Correction:
    """Result of a multiplicity correction over ``m`` hypotheses."""

    method: str
    alpha: float
    n_hypotheses: int
    raw_p: tuple[float, ...]
    adjusted_p: tuple[float, ...]
    rejected: tuple[bool, ...]

    @property
    def n_rejected(self) -> int:
        return int(sum(self.rejected))

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "alpha": self.alpha,
            "n_hypotheses": self.n_hypotheses,
            "n_rejected": self.n_rejected,
            "raw_p": list(self.raw_p),
            "adjusted_p": list(self.adjusted_p),
            "rejected": list(self.rejected),
        }


def family_wise_false_positive_probability(m: int, alpha: float = 0.05) -> float:
    """P(at least one false positive) for ``m`` independent tests at ``alpha``."""
    if m < 0:
        raise ValueError("m must be >= 0")
    return float(1.0 - (1.0 - alpha) ** m)


def _validate(p_values: np.ndarray, alpha: float) -> np.ndarray:
    p = np.asarray(p_values, dtype=float).ravel()
    if p.size and (np.any(p < 0.0) or np.any(p > 1.0)):
        raise ValueError("p-values must lie in [0, 1]")
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must lie in (0, 1)")
    return p


def holm(p_values, alpha: float = 0.05) -> Correction:
    """Holm step-down. FWER <= alpha under arbitrary dependence."""
    p = _validate(p_values, alpha)
    m = p.size
    if m == 0:
        return Correction("holm", alpha, 0, (), (), ())
    order = np.argsort(p, kind="stable")
    adjusted = np.empty(m, dtype=float)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[idx]))
        adjusted[idx] = running
    return Correction(
        "holm",
        alpha,
        m,
        tuple(p.tolist()),
        tuple(adjusted.tolist()),
        tuple((adjusted <= alpha).tolist()),
    )


def benjamini_hochberg(p_values, alpha: float = 0.05) -> Correction:
    """Benjamini-Hochberg step-up. FDR <= alpha under independence / PRDS."""
    p = _validate(p_values, alpha)
    m = p.size
    if m == 0:
        return Correction("benjamini_hochberg", alpha, 0, (), (), ())
    order = np.argsort(p, kind="stable")
    adjusted = np.empty(m, dtype=float)
    running = 1.0
    # walk from the largest p downwards, enforcing monotonicity
    for rank in range(m - 1, -1, -1):
        idx = order[rank]
        running = min(running, min(1.0, m / (rank + 1) * p[idx]))
        adjusted[idx] = running
    return Correction(
        "benjamini_hochberg",
        alpha,
        m,
        tuple(p.tolist()),
        tuple(adjusted.tolist()),
        tuple((adjusted <= alpha).tolist()),
    )


def romano_wolf(
    losses_candidates: np.ndarray,
    losses_baseline: np.ndarray,
    *,
    alpha: float = 0.05,
    n_boot: int = 2000,
    seed: int = 42,
) -> Correction:
    """Romano-Wolf step-down bootstrap. FWER <= alpha, exploits cross-model correlation.

    ``losses_candidates`` has shape ``(m, n)``: per-draw loss for each of ``m`` candidates.
    ``losses_baseline`` has shape ``(n,)``. Lower loss is better, so the one-sided
    alternative is "candidate loss < baseline loss".

    The bootstrap resamples *draws* (columns), which preserves the correlation between
    candidates induced by their sharing the same evaluation draws.
    """
    cand = np.atleast_2d(np.asarray(losses_candidates, dtype=float))
    base = np.asarray(losses_baseline, dtype=float).ravel()
    if cand.ndim != 2 or cand.shape[1] != base.size:
        raise ValueError("losses_candidates must have shape (m, n) matching baseline (n,)")
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must lie in (0, 1)")
    m, n = cand.shape
    if m == 0:
        return Correction("romano_wolf", alpha, 0, (), (), ())
    if n < 2:
        raise ValueError("need at least 2 draws to bootstrap")

    diff = base[None, :] - cand  # positive => candidate better
    theta = diff.mean(axis=1)
    sd = diff.std(axis=1, ddof=1)
    sd = np.where(sd <= 0, 1e-12, sd)
    stat = theta / (sd / np.sqrt(n))

    rng = np.random.default_rng(seed)
    centered = diff - theta[:, None]
    boot = np.empty((n_boot, m), dtype=float)
    for b in range(n_boot):
        pick = rng.integers(0, n, size=n)
        sample = centered[:, pick]
        bsd = sample.std(axis=1, ddof=1)
        bsd = np.where(bsd <= 0, 1e-12, bsd)
        boot[b] = sample.mean(axis=1) / (bsd / np.sqrt(n))

    adjusted = np.ones(m, dtype=float)
    remaining = list(np.argsort(-stat, kind="stable"))
    running = 0.0
    while remaining:
        idx = remaining[0]
        max_null = boot[:, remaining].max(axis=1)
        p_step = float((max_null >= stat[idx]).mean())
        running = max(running, min(1.0, p_step))
        adjusted[idx] = running
        remaining.pop(0)

    raw = np.array([float((boot[:, j] >= stat[j]).mean()) for j in range(m)])
    return Correction(
        "romano_wolf",
        alpha,
        m,
        tuple(raw.tolist()),
        tuple(adjusted.tolist()),
        tuple((adjusted <= alpha).tolist()),
    )


def paired_bootstrap_p(
    candidate_losses,
    baseline_losses,
    *,
    n_boot: int = 5000,
    seed: int = 42,
    alternative: str = "less",
) -> dict[str, float]:
    """Paired bootstrap for the mean loss difference (candidate - baseline).

    ``alternative='less'`` tests whether the candidate has *lower* loss. Returns the point
    estimate, a bootstrap 95% interval and the one- or two-sided p-value.
    """
    a = np.asarray(candidate_losses, dtype=float).ravel()
    b = np.asarray(baseline_losses, dtype=float).ravel()
    if a.size != b.size:
        raise ValueError("paired losses must align")
    if a.size < 2:
        raise ValueError("need at least 2 paired observations")
    if alternative not in ("less", "greater", "two-sided"):
        raise ValueError("alternative must be less, greater or two-sided")
    d = a - b
    theta = float(d.mean())
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, d.size, size=(n_boot, d.size))
    boot = d[idx].mean(axis=1)
    null = boot - theta
    if alternative == "less":
        p = float((null <= theta).mean())
    elif alternative == "greater":
        p = float((null >= theta).mean())
    else:
        p = float((np.abs(null) >= abs(theta)).mean())
    lo, hi = np.quantile(boot, [0.025, 0.975])
    return {
        "delta": theta,
        "ci_low": float(lo),
        "ci_high": float(hi),
        "p_value": min(1.0, max(0.0, p)),
        "n": int(d.size),
        "alternative": alternative,
    }


def correct(p_values, *, method: str = "holm", alpha: float = 0.05) -> Correction:
    """Dispatch to a correction by name. ``method='none'`` passes p-values through."""
    if method not in _METHODS:
        raise ValueError(f"unknown method={method!r}; available={list(_METHODS)}")
    if method == "holm":
        return holm(p_values, alpha)
    if method == "benjamini_hochberg":
        return benjamini_hochberg(p_values, alpha)
    if method == "romano_wolf":
        raise ValueError("romano_wolf requires loss matrices; call romano_wolf() directly")
    p = _validate(p_values, alpha)
    return Correction(
        "none",
        alpha,
        p.size,
        tuple(p.tolist()),
        tuple(p.tolist()),
        tuple((p <= alpha).tolist()),
    )

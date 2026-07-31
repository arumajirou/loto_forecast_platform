"""Falsifiable leakage detection.

Constitution principle VI. A pipeline that leaks the target will report a good score, and no
amount of staring at the score reveals the leak. The only reliable detector is a *negative
control*: destroy the signal and check that the score collapses.

Three controls are implemented, in increasing strength:

``permutation``  Shuffle the labels within the development set only. Any model scoring
                 materially above the theoretical baseline on permuted labels is reading the
                 target through a side channel.

``time_shift``   Shift the label vector forward by one draw. Catches off-by-one alignment
                 bugs in feature construction, which permutation misses because a shifted
                 label is still "the wrong label".

``future_probe`` Assert that no feature column is computable only from rows at or after the
                 prediction index. Implemented as a direct index audit rather than a
                 statistical test, so it catches leaks that are too small to detect
                 statistically but still invalidate the protocol.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

__all__ = [
    "SentinelVerdict",
    "permutation_sentinel",
    "time_shift_sentinel",
    "audit_feature_causality",
    "run_sentinel_suite",
]

ScoreFn = Callable[[np.ndarray, np.ndarray], float]


@dataclass(frozen=True)
class SentinelVerdict:
    """Outcome of one negative control."""

    control: str
    observed: float
    baseline: float
    tolerance: float
    n_repeats: int
    tripped: bool
    detail: str = ""

    @property
    def margin(self) -> float:
        return self.observed - self.baseline

    def to_dict(self) -> dict[str, object]:
        return {
            "control": self.control,
            "observed": self.observed,
            "baseline": self.baseline,
            "margin": self.margin,
            "tolerance": self.tolerance,
            "n_repeats": self.n_repeats,
            "tripped": self.tripped,
            "detail": self.detail,
        }


def permutation_sentinel(
    fit_predict: Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray],
    features: np.ndarray,
    labels: np.ndarray,
    score: ScoreFn,
    *,
    baseline: float,
    higher_is_better: bool = True,
    tolerance: float = 0.0,
    n_repeats: int = 20,
    seed: int = 42,
) -> SentinelVerdict:
    """Refit on label-permuted data ``n_repeats`` times and score.

    ``baseline`` is the theoretical score of an uninformative predictor (e.g. the exact
    within-tau ceiling from :mod:`loto.evaluation.theory_general`). ``tolerance`` should be
    set from the sampling noise of the score at this ``n``, not guessed.
    """
    x = np.asarray(features)
    y = np.asarray(labels)
    if x.shape[0] != y.shape[0]:
        raise ValueError("features and labels must have the same number of rows")
    if n_repeats < 1:
        raise ValueError("n_repeats must be >= 1")
    rng = np.random.default_rng(seed)
    scores: list[float] = []
    for _ in range(n_repeats):
        shuffled = y[rng.permutation(y.shape[0])]
        prediction = fit_predict(x, shuffled, x)
        scores.append(float(score(shuffled, np.asarray(prediction))))
    observed = float(np.mean(scores))
    tripped = (
        observed > baseline + tolerance if higher_is_better else observed < baseline - tolerance
    )
    return SentinelVerdict(
        control="permutation",
        observed=observed,
        baseline=baseline,
        tolerance=tolerance,
        n_repeats=n_repeats,
        tripped=bool(tripped),
        detail=f"score sd over repeats={float(np.std(scores, ddof=1)) if len(scores) > 1 else 0.0:.6f}",
    )


def time_shift_sentinel(
    fit_predict: Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray],
    features: np.ndarray,
    labels: np.ndarray,
    score: ScoreFn,
    *,
    baseline: float,
    higher_is_better: bool = True,
    tolerance: float = 0.0,
    shift: int = 1,
) -> SentinelVerdict:
    """Score the model against labels shifted by ``shift`` draws.

    A pipeline with correct causality scores at baseline here. A pipeline that accidentally
    aligned feature row ``i`` with label row ``i+shift`` scores *well*, which is the tell.
    """
    x = np.asarray(features)
    y = np.asarray(labels)
    if shift < 1:
        raise ValueError("shift must be >= 1")
    if y.shape[0] <= shift:
        raise ValueError("not enough rows to apply the shift")
    x_cut, y_shift = x[:-shift], y[shift:]
    prediction = np.asarray(fit_predict(x_cut, y_shift, x_cut))
    observed = float(score(y_shift, prediction))
    tripped = (
        observed > baseline + tolerance if higher_is_better else observed < baseline - tolerance
    )
    return SentinelVerdict(
        control="time_shift",
        observed=observed,
        baseline=baseline,
        tolerance=tolerance,
        n_repeats=1,
        tripped=bool(tripped),
        detail=f"shift={shift}, rows={y_shift.shape[0]}",
    )


def audit_feature_causality(
    builder: Callable[[Sequence[float]], np.ndarray],
    series: Sequence[float],
    *,
    index: int,
) -> SentinelVerdict:
    """Deterministic causality audit for a feature builder.

    Builds features from the full series and from the series truncated at ``index``. If any
    feature value at row ``index`` differs, that feature consumed future rows. This is an
    exact test: it does not depend on sample size or effect size.
    """
    values = list(series)
    if not (0 <= index < len(values)):
        raise IndexError(f"index {index} outside series of length {len(values)}")
    full = np.asarray(builder(values), dtype=float)
    truncated = np.asarray(builder(values[: index + 1]), dtype=float)
    if full.ndim == 1:
        full = full.reshape(-1, 1)
        truncated = truncated.reshape(-1, 1)
    if truncated.shape[0] <= index:
        raise ValueError("builder returned fewer rows than the truncated input")
    a = full[index]
    b = truncated[index]
    diff = np.abs(np.nan_to_num(a) - np.nan_to_num(b))
    worst = float(diff.max()) if diff.size else 0.0
    offenders = [int(i) for i in np.flatnonzero(diff > 1e-12)]
    return SentinelVerdict(
        control="future_probe",
        observed=worst,
        baseline=0.0,
        tolerance=1e-12,
        n_repeats=1,
        tripped=bool(offenders),
        detail=f"row={index}, leaking_columns={offenders[:12]}",
    )


def run_sentinel_suite(verdicts: list[SentinelVerdict]) -> dict[str, object]:
    """Aggregate verdicts into a single run-level status.

    ``SENTINEL_TRIPPED`` blocks promotion. ``SENTINEL_CLEAN`` does not prove absence of
    leakage -- it only records that these controls failed to find any, which is the honest
    framing.
    """
    tripped = [v for v in verdicts if v.tripped]
    return {
        "status": "SENTINEL_TRIPPED" if tripped else "SENTINEL_CLEAN",
        "promotion_allowed": not tripped,
        "n_controls": len(verdicts),
        "n_tripped": len(tripped),
        "tripped_controls": [v.control for v in tripped],
        "verdicts": [v.to_dict() for v in verdicts],
        "interpretation": (
            "one or more negative controls scored above chance; the protocol is invalid"
            if tripped
            else "no leakage detected by these controls; absence of evidence only"
        ),
    }

"""Statistically defensible leaderboard construction.

The v2.1.0 leaderboard sorted models by a weighted composite score and reported rank 1 as the
"champion". Three things were wrong with that:

1. No sample size, dispersion or interval accompanied any point estimate, so rank 1 could not
   be distinguished from rank 5.
2. No multiplicity correction, so sweeping N models against a baseline guaranteed a spurious
   winner.
3. The composite weighted ``ece`` negatively, and the constant-prediction baseline attains
   ``ece == 0`` by construction, so the objective structurally rewarded the trivial model.

This module fixes all three. Ranking requires per-draw losses, not just aggregates, because
significance is not recoverable from a mean. A model that cannot supply per-draw losses is
listed as ``UNRANKED`` rather than being ranked on an aggregate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from loto.evaluation.multiplicity import Correction, correct, paired_bootstrap_p, romano_wolf
from loto.evaluation.protocol import assert_comparable

__all__ = [
    "ModelResult",
    "LeaderboardRow",
    "Leaderboard",
    "build_leaderboard",
    "composite_score",
]


@dataclass
class ModelResult:
    """One model's evaluation output under a single protocol."""

    model_id: str
    protocol_hash: str
    metrics: dict[str, float]
    per_draw_loss: np.ndarray | None = None
    """Per-draw loss, lower better. Required for significance testing."""
    is_control: bool = False
    elapsed_seconds: float = 0.0
    status: str = "SUCCEEDED"
    notes: str = ""

    @property
    def rankable(self) -> bool:
        return (
            self.status == "SUCCEEDED"
            and self.per_draw_loss is not None
            and np.asarray(self.per_draw_loss).size >= 2
        )


@dataclass
class LeaderboardRow:
    rank: int | None
    model_id: str
    status: str
    is_control: bool
    point_estimate: float
    n: int
    sd: float
    se: float
    ci_low: float
    ci_high: float
    delta_vs_baseline: float
    raw_p: float
    adjusted_p: float
    significant: bool
    metrics: dict[str, float] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "rank": self.rank,
            "model_id": self.model_id,
            "status": self.status,
            "is_control": self.is_control,
            "point_estimate": self.point_estimate,
            "n": self.n,
            "sd": self.sd,
            "se": self.se,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "delta_vs_baseline": self.delta_vs_baseline,
            "raw_p": self.raw_p,
            "adjusted_p": self.adjusted_p,
            "significant": self.significant,
            "elapsed_seconds": self.elapsed_seconds,
            "notes": self.notes,
            **{f"metric_{k}": v for k, v in sorted(self.metrics.items())},
        }


@dataclass
class Leaderboard:
    protocol_hash: str
    baseline_model_id: str
    loss_name: str
    correction_method: str
    alpha: float
    rows: list[LeaderboardRow]
    correction: Correction | None
    unranked: list[str]
    n_significant: int
    verdict: str
    interpretation: str

    @property
    def champion(self) -> LeaderboardRow | None:
        """The best model *that beat the baseline significantly*. Otherwise ``None``.

        Returning ``None`` rather than "the top row" is the whole point: on i.i.d. data the
        honest answer is that no model won, and a leaderboard that always names a champion
        cannot express that.
        """
        for row in self.rows:
            if row.significant and not row.is_control:
                return row
        return None

    def to_dict(self) -> dict[str, object]:
        champion = self.champion
        return {
            "protocol_hash": self.protocol_hash,
            "baseline_model_id": self.baseline_model_id,
            "loss_name": self.loss_name,
            "correction_method": self.correction_method,
            "alpha": self.alpha,
            "n_models": len(self.rows),
            "n_significant": self.n_significant,
            "verdict": self.verdict,
            "interpretation": self.interpretation,
            "champion": champion.to_dict() if champion else None,
            "unranked": self.unranked,
            "rows": [r.to_dict() for r in self.rows],
        }


def composite_score(
    metrics: dict[str, float], weights: dict[str, float], *, forbid_degenerate: bool = True
) -> float:
    """Weighted metric combination with a guard against degenerate-metric exploitation.

    ``forbid_degenerate`` rejects a weight set that assigns non-zero weight to ``ece`` without
    also weighting a *sharpness* term. A constant predictor attains ``ece == 0`` exactly, so
    weighting calibration alone hands the trivial model a free win -- which is precisely how
    the v2.1.0 objective produced ``uniform`` as champion.
    """
    if forbid_degenerate and weights.get("ece"):
        sharpness_keys = {"brier", "log_loss", "interval_score", "sharpness", "brier_skill_score"}
        if not any(weights.get(k) for k in sharpness_keys):
            raise ValueError(
                "weighting 'ece' without a sharpness term is degenerate: a constant predictor "
                "attains ece=0 by construction. Add a brier/log_loss/interval_score weight."
            )
    missing = [k for k in weights if k not in metrics]
    if missing:
        raise KeyError(f"objective references absent metrics: {sorted(missing)}")
    return float(sum(w * float(metrics[k]) for k, w in weights.items()))


def build_leaderboard(
    results: Sequence[ModelResult],
    *,
    baseline_model_id: str,
    loss_name: str = "loss",
    correction_method: str = "romano_wolf",
    alpha: float = 0.05,
    n_boot: int = 2000,
    seed: int = 42,
) -> Leaderboard:
    """Rank models against a baseline with multiplicity control.

    Raises :class:`~loto.evaluation.protocol.ProtocolMismatch` when the results were not all
    produced under the same ``protocol_hash``.
    """
    if not results:
        raise ValueError("no results to rank")
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must lie in (0, 1)")

    protocol = assert_comparable(
        [{"protocol_hash": r.protocol_hash, "model_id": r.model_id} for r in results]
    )

    by_id = {r.model_id: r for r in results}
    if baseline_model_id not in by_id:
        raise KeyError(
            f"baseline {baseline_model_id!r} absent from results; available={sorted(by_id)[:10]}"
        )
    baseline = by_id[baseline_model_id]
    if not baseline.rankable:
        raise ValueError(
            f"baseline {baseline_model_id!r} has no per-draw losses; significance testing "
            "is impossible without a paired baseline"
        )
    base_loss = np.asarray(baseline.per_draw_loss, dtype=float).ravel()

    candidates: list[ModelResult] = []
    unranked: list[str] = []
    for r in results:
        if r.model_id == baseline_model_id:
            continue
        if not r.rankable:
            unranked.append(r.model_id)
            continue
        loss = np.asarray(r.per_draw_loss, dtype=float).ravel()
        if loss.size != base_loss.size:
            unranked.append(r.model_id)
            continue
        candidates.append(r)

    rows: list[LeaderboardRow] = []
    correction: Correction | None = None

    if candidates:
        matrix = np.vstack([np.asarray(c.per_draw_loss, dtype=float).ravel() for c in candidates])
        if correction_method == "romano_wolf":
            correction = romano_wolf(matrix, base_loss, alpha=alpha, n_boot=n_boot, seed=seed)
        else:
            raw = [
                paired_bootstrap_p(
                    np.asarray(c.per_draw_loss).ravel(),
                    base_loss,
                    n_boot=n_boot,
                    seed=seed,
                    alternative="less",
                )["p_value"]
                for c in candidates
            ]
            correction = correct(raw, method=correction_method, alpha=alpha)

        for idx, candidate in enumerate(candidates):
            loss = np.asarray(candidate.per_draw_loss, dtype=float).ravel()
            boot = paired_bootstrap_p(loss, base_loss, n_boot=n_boot, seed=seed, alternative="less")
            rows.append(
                LeaderboardRow(
                    rank=None,
                    model_id=candidate.model_id,
                    status=candidate.status,
                    is_control=candidate.is_control,
                    point_estimate=float(loss.mean()),
                    n=int(loss.size),
                    sd=float(loss.std(ddof=1)),
                    se=float(loss.std(ddof=1) / np.sqrt(loss.size)),
                    ci_low=boot["ci_low"] + float(base_loss.mean()),
                    ci_high=boot["ci_high"] + float(base_loss.mean()),
                    delta_vs_baseline=boot["delta"],
                    raw_p=correction.raw_p[idx],
                    adjusted_p=correction.adjusted_p[idx],
                    significant=bool(correction.rejected[idx]),
                    metrics=dict(candidate.metrics),
                    elapsed_seconds=candidate.elapsed_seconds,
                    notes=candidate.notes,
                )
            )

    rows.append(
        LeaderboardRow(
            rank=None,
            model_id=baseline.model_id,
            status=baseline.status,
            is_control=True,
            point_estimate=float(base_loss.mean()),
            n=int(base_loss.size),
            sd=float(base_loss.std(ddof=1)),
            se=float(base_loss.std(ddof=1) / np.sqrt(base_loss.size)),
            ci_low=float("nan"),
            ci_high=float("nan"),
            delta_vs_baseline=0.0,
            raw_p=1.0,
            adjusted_p=1.0,
            significant=False,
            metrics=dict(baseline.metrics),
            elapsed_seconds=baseline.elapsed_seconds,
            notes="baseline",
        )
    )

    rows.sort(key=lambda r: (r.adjusted_p, r.point_estimate, r.model_id))
    for position, row in enumerate(rows, start=1):
        row.rank = position

    n_sig = sum(1 for r in rows if r.significant and not r.is_control)
    if n_sig == 0:
        verdict = "NO_MODEL_BEATS_BASELINE"
        interpretation = (
            f"after {correction_method} correction over {len(candidates)} candidates at "
            f"alpha={alpha}, no model significantly beat {baseline_model_id!r} on {loss_name}. "
            "This is the expected result for an i.i.d. target and is NOT a pipeline failure."
        )
    else:
        verdict = "CANDIDATE_BEATS_BASELINE"
        interpretation = (
            f"{n_sig} model(s) beat {baseline_model_id!r} at multiplicity-corrected "
            f"alpha={alpha}. Verify the leakage sentinel before promoting."
        )

    return Leaderboard(
        protocol_hash=protocol,
        baseline_model_id=baseline_model_id,
        loss_name=loss_name,
        correction_method=correction_method,
        alpha=alpha,
        rows=rows,
        correction=correction,
        unranked=sorted(unranked),
        n_significant=n_sig,
        verdict=verdict,
        interpretation=interpretation,
    )


__all__.append("ProtocolMismatch")

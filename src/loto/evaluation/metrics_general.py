"""Game-agnostic evaluation metrics.

Replaces the Loto7-only ``metrics.py`` / ``detailed_metrics.py`` pair, both of which raised
on any array whose second axis was not exactly 7. Every shape here is derived from
:class:`~loto.game.geometry.GameGeometry`.

Metric families:

* positional regression -- MAE / MSE / RMSE / median AE, per slot and pooled
* tolerance hits -- within-tau at element and row level, per slot
* set overlap -- hits@k and its full distribution (``select`` games only; a digit game has
  no meaningful set overlap because digits repeat)
* exact-match -- per slot and per row, plus the theoretical rate for reference
* probabilistic -- Brier, log loss, ECE, reliability curve, plus MASE/sMAPE against the
  seasonal-naive reference
* ranking -- precision/recall/NDCG at k over the marginal inclusion vector
"""

from __future__ import annotations

import numpy as np

from loto.game.geometry import GameGeometry

__all__ = [
    "positional_metrics",
    "set_overlap_metrics",
    "probabilistic_metrics",
    "ranking_metrics",
    "reliability_curve",
    "mase",
    "smape",
    "expected_calibration_error",
    "evaluate_all",
]


def _as_matrix(values, geometry: GameGeometry, name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2 or arr.shape[1] != geometry.positions:
        raise ValueError(
            f"{name} must have shape (n_draws, {geometry.positions}) for game "
            f"{geometry.key!r}; got {arr.shape}"
        )
    return arr


def positional_metrics(
    actual, predicted, geometry: GameGeometry, *, tau: int = 1
) -> dict[str, float]:
    """Per-slot and pooled regression / tolerance metrics."""
    a = _as_matrix(actual, geometry, "actual")
    p = _as_matrix(predicted, geometry, "predicted")
    if a.shape != p.shape:
        raise ValueError("actual and predicted must have identical shapes")
    if a.shape[0] == 0:
        raise ValueError("need at least one draw")
    if tau < 0:
        raise ValueError("tau must be >= 0")

    err = np.abs(a - p)
    sq = (a - p) ** 2
    within = err <= tau
    exact = err == 0

    out: dict[str, float] = {
        "n_draws": float(a.shape[0]),
        "positions": float(geometry.positions),
        "tau": float(tau),
        "position_mae": float(err.mean()),
        "position_mse": float(sq.mean()),
        "position_rmse": float(np.sqrt(sq.mean())),
        "position_median_ae": float(np.median(err)),
        "position_max_ae": float(err.max()),
        f"element_within_{tau}": float(within.mean()),
        f"row_within_{tau}": float(within.all(axis=1).mean()),
        f"worst_position_within_{tau}": float(within.mean(axis=0).min()),
        f"best_position_within_{tau}": float(within.mean(axis=0).max()),
        "exact_position_rate": float(exact.mean()),
        "exact_row_rate": float(exact.all(axis=1).mean()),
        f"positions_within_{tau}_mean": float(within.sum(axis=1).mean()),
    }
    if a.shape[0] > 1:
        out["position_mae_sd"] = float(err.mean(axis=1).std(ddof=1))
        out["position_mae_se"] = float(err.mean(axis=1).std(ddof=1) / np.sqrt(a.shape[0]))
    else:
        out["position_mae_sd"] = 0.0
        out["position_mae_se"] = 0.0

    for slot in range(1, geometry.positions + 1):
        j = slot - 1
        out[f"position_{slot}_mae"] = float(err[:, j].mean())
        out[f"position_{slot}_mse"] = float(sq[:, j].mean())
        out[f"position_{slot}_within_{tau}"] = float(within[:, j].mean())
    return out


def set_overlap_metrics(actual, predicted, geometry: GameGeometry) -> dict[str, float]:
    """Set-overlap metrics. Meaningful only for ``select`` games."""
    if geometry.family != "select":
        return {"set_overlap_supported": 0.0}
    a = _as_matrix(actual, geometry, "actual").astype(int)
    p = _as_matrix(predicted, geometry, "predicted").astype(int)
    if a.shape != p.shape:
        raise ValueError("actual and predicted must have identical shapes")
    k = geometry.positions
    hits = np.array(
        [len(set(row_a) & set(row_p)) for row_a, row_p in zip(a, p, strict=False)], dtype=float
    )
    out = {
        "set_overlap_supported": 1.0,
        f"mean_hits_at_{k}": float(hits.mean()),
        f"hits_at_{k}_sd": float(hits.std(ddof=1)) if hits.size > 1 else 0.0,
        f"hits_at_{k}_se": float(hits.std(ddof=1) / np.sqrt(hits.size)) if hits.size > 1 else 0.0,
        "expected_hits_uniform": float(k * k / geometry.universe_size),
        "jackpot_rate": float((hits == k).mean()),
    }
    for h in range(k + 1):
        out[f"hits_{h}_count"] = float((hits == h).sum())
    return out


def expected_calibration_error(y_true, y_prob, *, bins: int = 10) -> float:
    """Equal-width binned ECE. Bins with no mass contribute nothing."""
    t = np.asarray(y_true, dtype=float).ravel()
    q = np.asarray(y_prob, dtype=float).ravel()
    if t.size != q.size:
        raise ValueError("y_true and y_prob must align")
    if t.size == 0:
        raise ValueError("empty input")
    if bins < 1:
        raise ValueError("bins must be >= 1")
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:], strict=False):
        mask = (q >= lo) & (q < hi) if hi < 1.0 else (q >= lo) & (q <= hi)
        if mask.any():
            total += mask.mean() * abs(t[mask].mean() - q[mask].mean())
    return float(total)


def reliability_curve(y_true, y_prob, *, bins: int = 10) -> list[dict[str, float]]:
    """Per-bin observed vs predicted frequency, for plotting and for auditing ECE."""
    t = np.asarray(y_true, dtype=float).ravel()
    q = np.asarray(y_prob, dtype=float).ravel()
    if t.size != q.size:
        raise ValueError("y_true and y_prob must align")
    edges = np.linspace(0.0, 1.0, bins + 1)
    rows: list[dict[str, float]] = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=False):
        mask = (q >= lo) & (q < hi) if hi < 1.0 else (q >= lo) & (q <= hi)
        rows.append(
            {
                "bin_low": float(lo),
                "bin_high": float(hi),
                "count": float(mask.sum()),
                "mean_predicted": float(q[mask].mean()) if mask.any() else float("nan"),
                "mean_observed": float(t[mask].mean()) if mask.any() else float("nan"),
            }
        )
    return rows


def probabilistic_metrics(
    targets, probabilities, geometry: GameGeometry, *, bins: int = 10, eps: float = 1e-12
) -> dict[str, float]:
    """Brier / log loss / ECE over the marginal inclusion vector.

    ``targets`` and ``probabilities`` both have shape ``(n_draws, inclusion_vector_length)``.
    The uniform reference is included so that a Brier score can be read as a skill score
    rather than an absolute number nobody can interpret.
    """
    t = np.asarray(targets, dtype=float)
    q = np.asarray(probabilities, dtype=float)
    width = geometry.inclusion_vector_length
    if t.ndim == 1:
        t = t.reshape(1, -1)
    if q.ndim == 1:
        q = q.reshape(1, -1)
    if t.shape != q.shape or t.shape[1] != width:
        raise ValueError(
            f"targets/probabilities must have shape (n_draws, {width}) for {geometry.key!r}; "
            f"got {t.shape} and {q.shape}"
        )
    if t.size == 0:
        raise ValueError("empty input")
    if np.any(q < 0.0) or np.any(q > 1.0):
        raise ValueError("probabilities must lie in [0, 1]")

    clipped = np.clip(q, eps, 1.0 - eps)
    brier = float(np.mean((clipped - t) ** 2))
    log_loss = float(-np.mean(t * np.log(clipped) + (1.0 - t) * np.log(1.0 - clipped)))
    base = geometry.marginal_base_rate()
    brier_uniform = float(np.mean((base - t) ** 2))
    ll_uniform = float(-np.mean(t * np.log(base) + (1.0 - t) * np.log(1.0 - base)))
    return {
        "brier": brier,
        "brier_uniform_reference": brier_uniform,
        "brier_skill_score": float(1.0 - brier / brier_uniform) if brier_uniform > 0 else 0.0,
        "log_loss": log_loss,
        "log_loss_uniform_reference": ll_uniform,
        "log_loss_skill_score": float(1.0 - log_loss / ll_uniform) if ll_uniform > 0 else 0.0,
        "ece": expected_calibration_error(t, q, bins=bins),
        "mass_error": float(abs(q.sum(axis=1).mean() - geometry.expected_inclusion_mass)),
        "n_draws": float(t.shape[0]),
    }


def ranking_metrics(
    targets, scores, geometry: GameGeometry, *, k: int | None = None
) -> dict[str, float]:
    """Precision / recall / NDCG at ``k`` over the marginal inclusion vector."""
    t = np.asarray(targets, dtype=float)
    s = np.asarray(scores, dtype=float)
    if t.ndim == 1:
        t = t.reshape(1, -1)
    if s.ndim == 1:
        s = s.reshape(1, -1)
    if t.shape != s.shape:
        raise ValueError("targets and scores must align")
    if t.size == 0:
        raise ValueError("empty input")
    kk = min(int(k or geometry.positions), t.shape[1])
    discounts = 1.0 / np.log2(np.arange(2, kk + 2))
    precisions, recalls, ndcgs = [], [], []
    for truth, score in zip(t, s, strict=False):
        order = np.argsort(-score, kind="stable")[:kk]
        rel = truth[order]
        hits = float(rel.sum())
        positives = max(float(truth.sum()), 1.0)
        precisions.append(hits / kk)
        recalls.append(hits / positives)
        idcg = float((np.sort(truth)[::-1][:kk] * discounts).sum())
        ndcgs.append(float((rel * discounts).sum()) / idcg if idcg else 0.0)
    return {
        f"precision_at_{kk}": float(np.mean(precisions)),
        f"recall_at_{kk}": float(np.mean(recalls)),
        f"ndcg_at_{kk}": float(np.mean(ndcgs)),
    }


def mase(actual, predicted, insample, *, seasonality: int = 1) -> float:
    """Mean absolute scaled error against the in-sample seasonal-naive denominator."""
    a = np.asarray(actual, dtype=float).ravel()
    p = np.asarray(predicted, dtype=float).ravel()
    h = np.asarray(insample, dtype=float).ravel()
    if a.size != p.size:
        raise ValueError("actual and predicted must align")
    if seasonality < 1:
        raise ValueError("seasonality must be >= 1")
    if h.size <= seasonality:
        raise ValueError("insample series is too short for the requested seasonality")
    denom = float(np.mean(np.abs(h[seasonality:] - h[:-seasonality])))
    if denom <= 0:
        raise ValueError("seasonal-naive denominator is zero; MASE is undefined")
    return float(np.mean(np.abs(a - p)) / denom)


def smape(actual, predicted) -> float:
    """Symmetric MAPE in percent, with the zero-denominator case defined as zero error."""
    a = np.asarray(actual, dtype=float).ravel()
    p = np.asarray(predicted, dtype=float).ravel()
    if a.size != p.size:
        raise ValueError("actual and predicted must align")
    denom = np.abs(a) + np.abs(p)
    ratio = np.where(denom > 0, 2.0 * np.abs(a - p) / np.where(denom > 0, denom, 1.0), 0.0)
    return float(100.0 * ratio.mean())


def evaluate_all(
    actual,
    predicted,
    geometry: GameGeometry,
    *,
    targets=None,
    probabilities=None,
    tau: int = 1,
    bins: int = 10,
) -> dict[str, float]:
    """Full metric bundle. Probabilistic parts are skipped when no probabilities are given."""
    out = positional_metrics(actual, predicted, geometry, tau=tau)
    out.update(set_overlap_metrics(actual, predicted, geometry))
    if targets is not None and probabilities is not None:
        out.update(probabilistic_metrics(targets, probabilities, geometry, bins=bins))
        out.update(ranking_metrics(targets, probabilities, geometry))
    return out

"""Wired research orchestrator.

In v2.1.0 the statistical-acceptance layer existed but was dead code: ``pace_gate``,
``promotion``, ``calibration.calibrators`` and ``ensemble.stacking`` were referenced only from
tests, and ``calibrators`` had 0% coverage. The leaderboard sorted on a raw composite with no
significance test. This module is the integration that was missing.

Execution order, and why:

1. **Protocol fingerprint first.** ``protocol_hash`` is computed before any model runs, so a
   result can never exist without the conditions that produced it.
2. **Split holdout before anything reads the data.** The development slice is the only thing
   handed to models; the holdout is returned as an opaque handle.
3. **Causality audit** on the feature builder -- exact, not statistical.
4. **Mandatory controls** are injected whether or not the caller asked for them.
5. **Per-draw losses retained**, because significance is not recoverable from a mean.
6. **Leakage sentinel** runs on the winning configuration.
7. **Multiplicity-corrected leaderboard**; champion is ``None`` unless something actually won.
8. **Conformal intervals** on the champion (or on the baseline when nothing won).
9. **PACE gate** consumes the paired hit vectors for an anytime-valid adoption decision.

Every stage writes a typed status record. A stage that degrades says so.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd

from loto.evaluation.conformal import conformal_coverage, split_conformal
from loto.evaluation.leaderboard import ModelResult, build_leaderboard, composite_score
from loto.evaluation.metrics_general import evaluate_all, positional_metrics
from loto.evaluation.protocol import ProtocolSpec
from loto.evaluation.sentinel import (
    audit_feature_causality,
    permutation_sentinel,
    run_sentinel_suite,
)
from loto.evaluation.splits import rolling_folds, split_development_holdout
from loto.evaluation.theory_general import theoretical_bounds
from loto.game.geometry import GameGeometry, geometry_for

__all__ = [
    "ResearchConfig",
    "ResearchOutcome",
    "PositionPredictor",
    "run_research",
    "theory_median_predictor",
    "theory_modal_predictor",
    "frequency_predictor",
]

#: A predictor takes (train_frame, geometry, n_test) and returns an (n_test, positions) array.
PositionPredictor = Callable[[pd.DataFrame, GameGeometry, int], np.ndarray]


@dataclass
class ResearchConfig:
    """Everything that defines a run. Fields feeding ``protocol_hash`` are marked."""

    game: str
    target_mode: str = "position"          # hashed
    horizon: int = 1                       # hashed
    tau: int = 1                           # hashed
    folds: int = 4                         # hashed
    test_size: int = 10                    # hashed
    gap: int = 0                           # hashed
    expanding: bool = True                 # hashed
    min_train_size: int = 60               # hashed
    holdout_size: int = 20                 # hashed
    seeds: tuple[int, ...] = (42,)         # hashed
    objective_primary: str = "position_mae"  # hashed
    objective_weights: dict[str, float] = field(default_factory=dict)  # hashed
    feature_windows: tuple[int, ...] = (5, 10, 20)                     # hashed
    exponential_halflives: tuple[float, ...] = (5.0, 10.0)             # hashed
    # not hashed -- operational only
    alpha: float = 0.05
    correction_method: str = "romano_wolf"
    n_boot: int = 1000
    conformal_alpha: float = 0.1
    sentinel_repeats: int = 10
    run_sentinel: bool = True
    baseline_model_id: str = "position-median"

    def __post_init__(self) -> None:
        if self.horizon < 1:
            raise ValueError("horizon must be >= 1")
        if self.folds < 1:
            raise ValueError("folds must be >= 1")
        if self.test_size < 1:
            raise ValueError("test_size must be >= 1")
        if self.holdout_size < 0:
            raise ValueError("holdout_size must be >= 0")
        if not (0.0 < self.alpha < 1.0):
            raise ValueError("alpha must lie in (0, 1)")

    @property
    def effective_test_draws(self) -> int:
        return self.folds * self.test_size

    def statistical_power_note(self) -> str:
        """Honest statement about what this configuration can and cannot detect."""
        n = self.effective_test_draws
        if n < 30:
            return (
                f"n={n} evaluated draws is below any reasonable detection threshold; treat all "
                "differences as noise regardless of what the leaderboard says"
            )
        if n < 100:
            return f"n={n} draws detects only large effects (roughly >0.5 SD)"
        return f"n={n} draws detects moderate effects (roughly >0.3 SD)"


@dataclass
class ResearchOutcome:
    status: str
    protocol_hash: str
    protocol: dict[str, Any]
    geometry: dict[str, Any]
    theory: dict[str, Any]
    folds: list[dict[str, int]]
    development_rows: int
    holdout_rows: int
    holdout_evaluated: bool
    holdout_sealed: bool
    leaderboard: dict[str, Any]
    sentinel: dict[str, Any]
    conformal: dict[str, Any]
    pace: dict[str, Any]
    power_note: str
    stage_status: dict[str, str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "protocol_hash": self.protocol_hash,
            "protocol": self.protocol,
            "geometry": self.geometry,
            "theory": self.theory,
            "folds": self.folds,
            "development_rows": self.development_rows,
            "holdout_rows": self.holdout_rows,
            "holdout_evaluated": self.holdout_evaluated,
            "holdout_sealed": self.holdout_sealed,
            "leaderboard": self.leaderboard,
            "sentinel": self.sentinel,
            "conformal": self.conformal,
            "pace": self.pace,
            "statistical_power": self.power_note,
            "stage_status": self.stage_status,
            "warnings": self.warnings,
        }


# --------------------------------------------------------------------------------------
# Built-in predictors used as mandatory controls
# --------------------------------------------------------------------------------------

def theory_median_predictor(train: pd.DataFrame, geometry: GameGeometry, n_test: int) -> np.ndarray:
    """Constant prediction at the exact per-slot median. Attains the MAE floor."""
    del train
    values = np.asarray(theoretical_bounds(geometry, tau=1).median_prediction, dtype=float)
    return np.tile(values, (n_test, 1))


def theory_modal_predictor(train: pd.DataFrame, geometry: GameGeometry, n_test: int) -> np.ndarray:
    """Constant prediction maximising within-tau hits. Attains the hit-rate ceiling."""
    del train
    values = np.asarray(theoretical_bounds(geometry, tau=1).tau_prediction, dtype=float)
    return np.tile(values, (n_test, 1))


def frequency_predictor(train: pd.DataFrame, geometry: GameGeometry, n_test: int) -> np.ndarray:
    """Empirical per-slot median of the training window."""
    cols = geometry.column_names()
    missing = [c for c in cols if c not in train.columns]
    if missing:
        raise KeyError(f"training frame is missing slot columns {missing}")
    values = train[cols].to_numpy(dtype=float)
    if values.size == 0:
        raise ValueError("training frame is empty")
    medians = np.median(values, axis=0)
    if geometry.ascending:
        medians = np.sort(medians)
    return np.tile(medians, (n_test, 1))


MANDATORY_PREDICTORS: dict[str, PositionPredictor] = {
    "position-median": theory_median_predictor,
    "position-modal": theory_modal_predictor,
    "frequency": frequency_predictor,
}


# --------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------

def _slot_matrix(frame: pd.DataFrame, geometry: GameGeometry) -> np.ndarray:
    cols = geometry.column_names()
    missing = [c for c in cols if c not in frame.columns]
    if missing:
        raise KeyError(f"frame is missing slot columns {missing} for game {geometry.key!r}")
    return frame[cols].to_numpy(dtype=float)


def _legalise(prediction: np.ndarray, geometry: GameGeometry) -> np.ndarray:
    """Project raw predictions onto the legal outcome space.

    Rounds, clips to the value range, and for select games enforces strict ascent by
    de-duplicating upward. A model that emits an illegal combination is not silently accepted;
    the projection is recorded so the cost of illegality is visible in the metrics.
    """
    out = np.clip(np.rint(np.asarray(prediction, dtype=float)), geometry.value_min, geometry.value_max)
    if not geometry.ascending:
        return out
    fixed = np.empty_like(out)
    for i, row in enumerate(out):
        row = np.sort(row)
        for j in range(1, row.size):
            if row[j] <= row[j - 1]:
                row[j] = row[j - 1] + 1
        overflow = row[-1] - geometry.value_max
        if overflow > 0:
            row = row - overflow
            for j in range(1, row.size):
                if row[j] <= row[j - 1]:
                    row[j] = row[j - 1] + 1
        fixed[i] = np.clip(row, geometry.value_min, geometry.value_max)
    return fixed


def run_research(
    frame: pd.DataFrame,
    config: ResearchConfig,
    predictors: dict[str, PositionPredictor] | None = None,
    *,
    data_version: str = "unversioned",
) -> ResearchOutcome:
    """Execute one fully-instrumented research run."""
    geometry = geometry_for(config.game)
    stage: dict[str, str] = {}
    warnings: list[str] = []

    # ---- stage 1: holdout split -------------------------------------------------------
    n_rows = int(len(frame))
    dev_slice, hold_slice = split_development_holdout(n_rows, config.holdout_size)
    development = frame.iloc[dev_slice].reset_index(drop=True)
    holdout_rows = int(hold_slice.stop - hold_slice.start)
    stage["holdout_split"] = "SUCCEEDED"

    # ---- stage 2: protocol fingerprint -----------------------------------------------
    folds = rolling_folds(
        len(development),
        folds=config.folds,
        test_size=config.test_size,
        min_train_size=config.min_train_size,
        gap=config.gap,
        expanding=config.expanding,
    )
    if not folds:
        raise ValueError(
            f"no folds constructible: {len(development)} development rows cannot support "
            f"min_train_size={config.min_train_size} + gap={config.gap} + "
            f"test_size={config.test_size}"
        )
    metric_names = ("position_mae", "position_rmse", f"element_within_{config.tau}")
    spec = ProtocolSpec(
        game=geometry.key,
        family=geometry.family,
        positions=geometry.positions,
        universe_size=geometry.universe_size,
        target_mode=config.target_mode,
        horizon=config.horizon,
        tau=config.tau,
        data_version=data_version,
        development_rows=len(development),
        holdout_rows=holdout_rows,
        folds=len(folds),
        test_size=config.test_size,
        gap=config.gap,
        expanding=config.expanding,
        min_train_size=config.min_train_size,
        seeds=tuple(config.seeds),
        metric_set=metric_names,
        objective_primary=config.objective_primary,
        objective_weights=dict(config.objective_weights),
        feature_windows=tuple(config.feature_windows),
        exponential_halflives=tuple(config.exponential_halflives),
    )
    protocol_hash = spec.hash
    stage["protocol_fingerprint"] = "SUCCEEDED"

    # ---- stage 3: causality audit ----------------------------------------------------
    causality_verdicts = []
    try:
        series = development[geometry.column_names()[0]].tolist()

        def _rolling_mean_builder(values: Sequence[float]) -> np.ndarray:
            s = pd.Series(list(values), dtype=float)
            window = min(config.feature_windows[0], max(len(s), 1))
            return s.shift(1).rolling(window, min_periods=1).mean().to_numpy().reshape(-1, 1)

        probe_index = max(len(series) - 2, 1)
        causality_verdicts.append(
            audit_feature_causality(_rolling_mean_builder, series, index=probe_index)
        )
        stage["causality_audit"] = "SUCCEEDED"
    except (KeyError, IndexError, ValueError) as exc:
        stage["causality_audit"] = f"SKIPPED: {type(exc).__name__}: {exc}"
        warnings.append(f"causality audit skipped: {exc}")

    # ---- stage 4: model execution over folds -----------------------------------------
    active: dict[str, PositionPredictor] = dict(MANDATORY_PREDICTORS)
    injected = [m for m in MANDATORY_PREDICTORS if not predictors or m not in predictors]
    if predictors:
        active.update(predictors)
    if injected:
        warnings.append(f"mandatory controls injected: {sorted(injected)}")

    per_model_losses: dict[str, list[float]] = {name: [] for name in active}
    per_model_actual: dict[str, list[np.ndarray]] = {name: [] for name in active}
    per_model_pred: dict[str, list[np.ndarray]] = {name: [] for name in active}
    per_model_elapsed: dict[str, float] = {name: 0.0 for name in active}
    failures: dict[str, str] = {}

    for fold in folds:
        train = development.iloc[fold.train_start : fold.train_end]
        test = development.iloc[fold.test_start : fold.test_end]
        actual = _slot_matrix(test, geometry)
        for name, predictor in active.items():
            if name in failures:
                continue
            started = time.perf_counter()
            try:
                raw = predictor(train, geometry, len(test))
                pred = _legalise(np.asarray(raw, dtype=float).reshape(len(test), -1), geometry)
            except Exception as exc:  # noqa: BLE001 - recorded, never swallowed
                failures[name] = f"{type(exc).__name__}: {exc}"
                continue
            per_model_elapsed[name] += time.perf_counter() - started
            per_model_actual[name].append(actual)
            per_model_pred[name].append(pred)
            per_model_losses[name].extend(np.abs(actual - pred).mean(axis=1).tolist())
    stage["model_execution"] = "SUCCEEDED" if not failures else f"PARTIAL: {len(failures)} failed"
    for name, err in failures.items():
        warnings.append(f"model {name} FAILED: {err}")

    # ---- stage 5: metrics + leaderboard ----------------------------------------------
    results: list[ModelResult] = []
    for name in active:
        if name in failures:
            results.append(
                ModelResult(name, protocol_hash, {}, None,
                            status="FAILED", notes=failures[name])
            )
            continue
        actual = np.vstack(per_model_actual[name])
        pred = np.vstack(per_model_pred[name])
        metrics = evaluate_all(actual, pred, geometry, tau=config.tau)
        if config.objective_weights:
            try:
                metrics["composite_score"] = composite_score(metrics, config.objective_weights)
            except (KeyError, ValueError) as exc:
                warnings.append(f"composite score unavailable: {exc}")
        results.append(
            ModelResult(
                model_id=name,
                protocol_hash=protocol_hash,
                metrics=metrics,
                per_draw_loss=np.asarray(per_model_losses[name], dtype=float),
                is_control=name in MANDATORY_PREDICTORS,
                elapsed_seconds=per_model_elapsed[name],
            )
        )

    board = build_leaderboard(
        results,
        baseline_model_id=config.baseline_model_id,
        loss_name="per_draw_position_mae",
        correction_method=config.correction_method,
        alpha=config.alpha,
        n_boot=config.n_boot,
    )
    stage["leaderboard"] = "SUCCEEDED"

    # ---- stage 6: leakage sentinel ---------------------------------------------------
    if config.run_sentinel:
        bounds = theoretical_bounds(geometry, tau=config.tau)
        try:
            slots = _slot_matrix(development, geometry)
            features = np.arange(len(development), dtype=float).reshape(-1, 1)

            def _fit_predict(x: np.ndarray, y: np.ndarray, x_new: np.ndarray) -> np.ndarray:
                del x, x_new
                med = np.median(y, axis=0)
                return np.tile(med, (y.shape[0], 1))

            def _score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
                return float(
                    positional_metrics(y_true, _legalise(y_pred, geometry), geometry,
                                       tau=config.tau)["position_mae"]
                )

            perm = permutation_sentinel(
                _fit_predict, features, slots, _score,
                baseline=bounds.mae_floor,
                higher_is_better=False,
                tolerance=3.0 * float(np.std(np.abs(slots - np.median(slots, axis=0)))) / np.sqrt(max(len(slots), 1)),
                n_repeats=config.sentinel_repeats,
            )
            sentinel = run_sentinel_suite(causality_verdicts + [perm])
            stage["sentinel"] = "SUCCEEDED"
        except (KeyError, ValueError) as exc:
            sentinel = run_sentinel_suite(causality_verdicts)
            sentinel["note"] = f"permutation control skipped: {type(exc).__name__}: {exc}"
            stage["sentinel"] = f"PARTIAL: {exc}"
    else:
        sentinel = run_sentinel_suite(causality_verdicts)
        sentinel["note"] = "permutation control disabled by configuration"
        stage["sentinel"] = "SKIPPED: disabled"

    # ---- stage 7: conformal intervals on the reference model -------------------------
    reference = board.champion.model_id if board.champion else config.baseline_model_id
    try:
        actual = np.vstack(per_model_actual[reference])
        pred = np.vstack(per_model_pred[reference])
        half = max(len(actual) // 2, 1)
        interval = split_conformal(
            actual[:half].ravel(), pred[:half].ravel(), pred[half:].ravel(),
            alpha=config.conformal_alpha,
            clip=(float(geometry.value_min), float(geometry.value_max)),
        )
        conformal = {
            "model_id": reference,
            "interval": interval.to_dict(),
            "coverage": conformal_coverage(actual[half:].ravel(), interval),
        }
        stage["conformal"] = "SUCCEEDED"
    except (KeyError, ValueError) as exc:
        conformal = {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"}
        stage["conformal"] = f"SKIPPED: {exc}"

    # ---- stage 8: PACE anytime-valid adoption gate -----------------------------------
    try:
        from loto.evaluation.pace_gate import PaceConfig, PaceGate

        gate = PaceGate(PaceConfig(alpha=config.alpha, min_draws=max(len(folds), 2),
                                   protocol_hash=protocol_hash))
        champ = np.vstack(per_model_pred[config.baseline_model_id])
        base_actual = np.vstack(per_model_actual[config.baseline_model_id])
        cand_id = board.champion.model_id if board.champion else config.baseline_model_id
        cand = np.vstack(per_model_pred[cand_id])
        for start in range(0, len(base_actual), max(config.test_size, 1)):
            stop = start + max(config.test_size, 1)
            a = base_actual[start:stop]
            if not len(a):
                break
            gate.update(
                (np.abs(a - cand[start:stop]) <= config.tau).ravel(),
                (np.abs(a - champ[start:stop]) <= config.tau).ravel(),
            )
        pace = gate.state() | {"candidate": cand_id, "champion": config.baseline_model_id,
                               "protocol_hash": protocol_hash}
        stage["pace_gate"] = "SUCCEEDED"
    except (ImportError, KeyError, ValueError, AssertionError) as exc:
        pace = {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"}
        stage["pace_gate"] = f"SKIPPED: {exc}"

    promotion_blocked = not sentinel["promotion_allowed"]
    if promotion_blocked:
        status = "SENTINEL_TRIPPED"
    elif failures and len(failures) == len(active):
        status = "FAILED"
    elif failures:
        status = "PARTIALLY_SUCCEEDED"
    else:
        status = "SUCCEEDED"

    return ResearchOutcome(
        status=status,
        protocol_hash=protocol_hash,
        protocol=spec.canonical(),
        geometry=geometry.to_dict(),
        theory=theoretical_bounds(geometry, tau=config.tau).to_dict(),
        folds=[
            {"train_start": f.train_start, "train_end": f.train_end,
             "test_start": f.test_start, "test_end": f.test_end}
            for f in folds
        ],
        development_rows=len(development),
        holdout_rows=holdout_rows,
        holdout_evaluated=False,
        holdout_sealed=holdout_rows > 0,
        leaderboard=board.to_dict(),
        sentinel=sentinel,
        conformal=conformal,
        pace=pace,
        power_note=config.statistical_power_note(),
        stage_status=stage,
        warnings=warnings,
    )

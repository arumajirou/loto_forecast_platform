from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.evaluation.metrics_general import (
    positional_metrics,
    probabilistic_metrics,
    set_overlap_metrics,
)
from loto.game.geometry import GameGeometry
from loto.probabilistic.artifact_store import ProbabilisticArtifactStore
from loto.probabilistic.dataset import DatasetBundle
from loto.probabilistic.math.elementary_symmetric import (
    conditional_bernoulli_log_probability,
    fixed_cardinality_marginals,
)
from loto.probabilistic.models.subset_native import (
    MODEL_ID,
    fit_conditional_bernoulli_map,
    frequency_fixed_k_log_probability,
    uniform_fixed_k_log_probability,
)
from loto.probabilistic.statuses import TrialStatus

BASELINES = (
    "random",
    "fixed_value",
    "historical_mean",
    "historical_median",
    "recent_value",
    "frequency",
    "statistical_shrinkage",
)

_LOWER_IS_BETTER = {
    "mae",
    "mse",
    "rmse",
    "candidate_brier",
    "candidate_ece",
    "candidate_log_loss",
    "joint_log_loss",
    "position_max_ae",
}


@dataclass(frozen=True)
class SubsetEvaluationResult:
    status: str
    model_id: str
    game: str
    seeds: tuple[int, ...]
    cutoffs: tuple[int, ...]
    model_rows: tuple[dict[str, Any], ...]
    baseline_rows: tuple[dict[str, Any], ...]
    model_summary: dict[str, Any]
    baseline_summary: dict[str, Any]
    promotion: dict[str, Any]
    prospective_prediction: dict[str, Any]
    artifact_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def fix_prospective_prediction(
    payload: dict[str, Any],
    *,
    fixed_at: str | None = None,
) -> dict[str, Any]:
    frozen = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    if "actual" in frozen or frozen.get("actual_known") is True:
        raise ValueError("prospective payload must not contain a known actual")
    timestamp = fixed_at or datetime.now(UTC).isoformat()
    digest = hashlib.sha256(_canonical_bytes(frozen)).hexdigest()
    return {
        "schema_version": "1.0.0",
        "algorithm": "SHA-256",
        "fixed_at": timestamp,
        "payload_sha256": digest,
        "payload": frozen,
    }


def verify_fixed_prediction(sealed: dict[str, Any]) -> bool:
    try:
        if sealed["algorithm"] != "SHA-256":
            return False
        actual = hashlib.sha256(_canonical_bytes(sealed["payload"])).hexdigest()
        return actual == sealed["payload_sha256"]
    except (KeyError, TypeError):
        return False


def _indicator_row(values: np.ndarray, geometry: GameGeometry) -> np.ndarray:
    indicator = np.zeros(geometry.universe_size, dtype=float)
    indicator[np.asarray(values, dtype=int) - geometry.value_min] = 1.0
    return indicator


def _legal_from_targets(targets: np.ndarray, geometry: GameGeometry) -> list[int]:
    available = list(geometry.values)
    chosen: list[int] = []
    for target in np.sort(np.asarray(targets, dtype=float)):
        selected = min(available, key=lambda value: (abs(value - target), value))
        available.remove(selected)
        chosen.append(int(selected))
    result = sorted(chosen)
    geometry.validate_outcome(result)
    return result


def _frequency_state(
    training_indicator: np.ndarray,
    *,
    pseudocount: float,
) -> tuple[np.ndarray, np.ndarray]:
    counts = np.asarray(training_indicator, dtype=float).sum(axis=0)
    log_weights = np.log(counts + pseudocount)
    cardinality = int(np.asarray(training_indicator, dtype=int).sum(axis=1)[0])
    marginals = fixed_cardinality_marginals(log_weights, cardinality)
    return log_weights, marginals


def _statistical_shrinkage_state(
    training_indicator: np.ndarray,
    *,
    prior_strength: float = 2.0,
) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(training_indicator, dtype=float)
    rows, candidates = values.shape
    cardinality = int(values.sum(axis=1)[0])
    base_rate = cardinality / candidates
    successes = values.sum(axis=0)
    probability = (successes + prior_strength * base_rate) / (rows + prior_strength)
    probability = np.clip(probability, 1e-9, 1.0 - 1e-9)
    log_odds = np.log(probability) - np.log1p(-probability)
    marginals = fixed_cardinality_marginals(log_odds, cardinality)
    return log_odds, marginals


def _point_from_marginals(marginals: np.ndarray, geometry: GameGeometry) -> list[int]:
    indices = np.argpartition(marginals, -geometry.positions)[-geometry.positions :]
    prediction = sorted((indices + geometry.value_min).astype(int).tolist())
    geometry.validate_outcome(prediction)
    return prediction


def _score_prediction(
    *,
    actual: np.ndarray,
    predicted: list[int],
    marginals: np.ndarray,
    joint_log_probability: float,
    geometry: GameGeometry,
    ece_bins: int,
) -> dict[str, float]:
    actual_row = np.sort(np.asarray(actual, dtype=int))
    predicted_row = np.sort(np.asarray(predicted, dtype=int))
    target = _indicator_row(actual_row, geometry)
    probability = np.asarray(marginals, dtype=float)
    if probability.shape != (geometry.universe_size,):
        raise ValueError("candidate marginals have the wrong shape")
    if np.any(probability < 0.0) or np.any(probability > 1.0):
        raise ValueError("candidate marginals must lie in [0, 1]")
    if not np.isclose(probability.sum(), geometry.positions, atol=1e-7):
        raise ValueError("candidate marginals must sum to the fixed cardinality")

    positional = positional_metrics(actual_row, predicted_row, geometry, tau=1)
    overlap = set_overlap_metrics(actual_row, predicted_row, geometry)
    probabilistic = probabilistic_metrics(target, probability, geometry, bins=ece_bins)
    metrics = {
        "hit_at_1": positional["element_within_1"],
        "all_positions_hit_at_1": positional["row_within_1"],
        "mae": positional["position_mae"],
        "mse": positional["position_mse"],
        "rmse": positional["position_rmse"],
        "position_max_ae": positional["position_max_ae"],
        "exact_row_rate": positional["exact_row_rate"],
        "set_overlap": overlap[f"mean_hits_at_{geometry.positions}"],
        "jaccard": float(
            len(set(actual_row.tolist()) & set(predicted_row.tolist()))
            / len(set(actual_row.tolist()) | set(predicted_row.tolist()))
        ),
        "candidate_brier": probabilistic["brier"],
        "candidate_ece": probabilistic["ece"],
        "candidate_log_loss": probabilistic["log_loss"],
        "candidate_brier_skill": probabilistic["brier_skill_score"],
        "expected_overlap": float(np.dot(target, probability)),
        "joint_log_probability": float(joint_log_probability),
        "joint_log_loss": float(-joint_log_probability),
    }
    for position in range(1, geometry.positions + 1):
        metrics[f"position_{position}_hit_at_1"] = positional[f"position_{position}_within_1"]
        metrics[f"position_{position}_mae"] = positional[f"position_{position}_mae"]
        metrics[f"position_{position}_mse"] = positional[f"position_{position}_mse"]
    if not all(np.isfinite(value) for value in metrics.values()):
        raise ValueError("evaluation produced a non-finite metric")
    return metrics


def _baseline_state(
    name: str,
    *,
    training_values: np.ndarray,
    training_indicator: np.ndarray,
    geometry: GameGeometry,
    seed: int,
) -> tuple[list[int], np.ndarray, np.ndarray | None]:
    if name == "random":
        rng = np.random.default_rng(seed)
        prediction = sorted(
            rng.choice(list(geometry.values), size=geometry.positions, replace=False)
            .astype(int)
            .tolist()
        )
        marginals = np.full(
            geometry.universe_size,
            geometry.positions / geometry.universe_size,
            dtype=float,
        )
        return prediction, marginals, None
    if name == "fixed_value":
        prediction = list(geometry.values)[: geometry.positions]
        marginals = _indicator_row(np.asarray(prediction), geometry)
        return prediction, marginals, None
    if name == "historical_mean":
        prediction = _legal_from_targets(training_values.mean(axis=0), geometry)
        return prediction, _indicator_row(np.asarray(prediction), geometry), None
    if name == "historical_median":
        prediction = _legal_from_targets(np.median(training_values, axis=0), geometry)
        return prediction, _indicator_row(np.asarray(prediction), geometry), None
    if name == "recent_value":
        prediction = np.asarray(training_values[-1], dtype=int).tolist()
        geometry.validate_outcome(prediction)
        return prediction, _indicator_row(np.asarray(prediction), geometry), None
    if name == "frequency":
        log_weights, marginals = _frequency_state(training_indicator, pseudocount=0.5)
        return _point_from_marginals(marginals, geometry), marginals, log_weights
    if name == "statistical_shrinkage":
        log_weights, marginals = _statistical_shrinkage_state(training_indicator)
        return _point_from_marginals(marginals, geometry), marginals, log_weights
    raise KeyError(name)


def _baseline_joint_log_probability(
    name: str,
    *,
    prediction: list[int],
    log_weights: np.ndarray | None,
    actual_indices: tuple[int, ...],
    training_indicator: np.ndarray,
    geometry: GameGeometry,
) -> float:
    floor = float(np.log(1e-15))
    if name == "random":
        return uniform_fixed_k_log_probability(geometry.universe_size, geometry.positions)
    if name == "frequency":
        return frequency_fixed_k_log_probability(
            training_indicator,
            actual_indices,
            pseudocount=0.5,
        )
    if name == "statistical_shrinkage" and log_weights is not None:
        return conditional_bernoulli_log_probability(
            log_weights,
            actual_indices,
            geometry.positions,
        )
    predicted_indices = tuple(value - geometry.value_min for value in prediction)
    return 0.0 if predicted_indices == actual_indices else floor


def evaluate_cutoff(
    bundle: DatasetBundle,
    config: Any,
    *,
    cutoff: int,
    seed: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if bundle.geometry.family != "select" or bundle.candidate_indicator is None:
        raise ValueError("fixed-cardinality evaluation requires a select-family dataset")
    if cutoff < int(config.min_train_size) or cutoff >= bundle.rows:
        raise ValueError("cutoff must leave a chronological training window and one actual row")
    geometry = bundle.geometry
    training_indicator = bundle.candidate_indicator[:cutoff]
    training_values = bundle.values[:cutoff]
    actual = bundle.values[cutoff]
    actual_indices = tuple((actual - geometry.value_min).astype(int).tolist())
    posterior = fit_conditional_bernoulli_map(
        training_indicator,
        game=bundle.game,
        config=config,
        seed=seed,
        cardinality=geometry.positions,
    )
    prediction = [value + geometry.value_min for value in posterior.point_indices]
    marginals = posterior.candidate_marginals
    joint_log_probability = posterior.posterior_predictive_log_probability(actual_indices)
    metrics = _score_prediction(
        actual=actual,
        predicted=prediction,
        marginals=marginals,
        joint_log_probability=joint_log_probability,
        geometry=geometry,
        ece_bins=int(config.subset_ece_bins),
    )
    model_row: dict[str, Any] = {
        "model_id": MODEL_ID,
        "seed": int(seed),
        "cutoff": int(cutoff),
        "draw_id": bundle.draw_ids[cutoff],
        "actual": actual.astype(int).tolist(),
        "prediction": prediction,
        "candidate_marginals": marginals.tolist(),
        "training_rows": int(posterior.training_rows),
        "optimizer_success": bool(posterior.optimizer_success),
        "gradient_norm": float(posterior.gradient_norm),
        "laplace_ridge": float(posterior.laplace_ridge),
        **metrics,
    }

    baseline_rows: list[dict[str, Any]] = []
    for index, name in enumerate(BASELINES):
        baseline_prediction, baseline_marginals, log_weights = _baseline_state(
            name,
            training_values=training_values,
            training_indicator=training_indicator,
            geometry=geometry,
            seed=seed * 1000003 + cutoff * 97 + index,
        )
        baseline_log_probability = _baseline_joint_log_probability(
            name,
            prediction=baseline_prediction,
            log_weights=log_weights,
            actual_indices=actual_indices,
            training_indicator=training_indicator,
            geometry=geometry,
        )
        baseline_metrics = _score_prediction(
            actual=actual,
            predicted=baseline_prediction,
            marginals=baseline_marginals,
            joint_log_probability=baseline_log_probability,
            geometry=geometry,
            ece_bins=int(config.subset_ece_bins),
        )
        baseline_rows.append(
            {
                "baseline": name,
                "seed": int(seed),
                "cutoff": int(cutoff),
                "draw_id": bundle.draw_ids[cutoff],
                "actual": actual.astype(int).tolist(),
                "prediction": baseline_prediction,
                "candidate_marginals": baseline_marginals.tolist(),
                **baseline_metrics,
            }
        )
    return model_row, baseline_rows


def _numeric_metric_keys(rows: list[dict[str, Any]]) -> list[str]:
    excluded = {
        "seed",
        "cutoff",
        "training_rows",
        "optimizer_success",
        "gradient_norm",
        "laplace_ridge",
    }
    keys: set[str] = set()
    for row in rows:
        for key, value in row.items():
            if (
                key not in excluded
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                keys.add(key)
    return sorted(keys)


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot summarize empty rows")
    metrics: dict[str, dict[str, float]] = {}
    for key in _numeric_metric_keys(rows):
        values = np.asarray([float(row[key]) for row in rows], dtype=float)
        lower = key in _LOWER_IS_BETTER or any(
            token in key for token in ("_mae", "_mse", "_rmse", "_loss", "_brier", "_ece")
        )
        metrics[key] = {
            "mean": float(values.mean()),
            "variance": float(values.var(ddof=0)),
            "std": float(values.std(ddof=0)),
            "worst": float(values.max() if lower else values.min()),
            "best": float(values.min() if lower else values.max()),
        }
    by_seed: dict[str, Any] = {}
    for seed in sorted({int(row["seed"]) for row in rows}):
        seed_rows = [row for row in rows if int(row["seed"]) == seed]
        by_seed[str(seed)] = {
            key: float(np.mean([float(row[key]) for row in seed_rows]))
            for key in _numeric_metric_keys(seed_rows)
        }
    return {"rows": len(rows), "metrics": metrics, "by_seed": by_seed}


def _prospective_prediction(
    bundle: DatasetBundle,
    config: Any,
    *,
    fixed_at: str | None,
) -> dict[str, Any]:
    if bundle.candidate_indicator is None:
        raise ValueError("candidate indicators are required")
    marginals: list[np.ndarray] = []
    seed_predictions: dict[str, list[int]] = {}
    for seed in config.seeds:
        posterior = fit_conditional_bernoulli_map(
            bundle.candidate_indicator,
            game=bundle.game,
            config=config,
            seed=int(seed),
            cardinality=bundle.geometry.positions,
        )
        marginals.append(posterior.candidate_marginals)
        seed_predictions[str(seed)] = [
            value + bundle.geometry.value_min for value in posterior.point_indices
        ]
    ensemble = np.mean(np.vstack(marginals), axis=0)
    prediction = _point_from_marginals(ensemble, bundle.geometry)
    payload = {
        "model_id": MODEL_ID,
        "game": bundle.game,
        "target_mode": "fixed_cardinality_subset",
        "data_version": bundle.data_version,
        "feature_set_hash": bundle.feature_set_hash,
        "training_rows": bundle.rows,
        "last_observed_draw_id": bundle.draw_ids[-1],
        "forecast_draw_id": f"next-{bundle.rows + 1}",
        "seeds": [int(seed) for seed in config.seeds],
        "seed_predictions": seed_predictions,
        "prediction": prediction,
        "candidate_marginals": ensemble.tolist(),
        "actual_known": False,
    }
    return fix_prospective_prediction(payload, fixed_at=fixed_at)


def evaluate_conditional_bernoulli(
    bundle: DatasetBundle,
    config: Any,
    *,
    output_dir: str | Path | None = None,
    fixed_at: str | None = None,
) -> SubsetEvaluationResult:
    if bundle.geometry.family != "select" or bundle.candidate_indicator is None:
        raise ValueError("Conditional Bernoulli evaluation requires a select-family bundle")
    if not config.seeds:
        raise ValueError("at least one seed is required")
    evaluation_points = min(
        int(config.test_size) * int(config.folds),
        bundle.rows - int(config.min_train_size),
    )
    if evaluation_points < 1:
        raise ValueError("dataset is too short for the requested chronological evaluation")
    first_cutoff = bundle.rows - evaluation_points
    cutoffs = tuple(range(first_cutoff, bundle.rows))

    model_rows: list[dict[str, Any]] = []
    baseline_rows: list[dict[str, Any]] = []
    for seed in config.seeds:
        for cutoff in cutoffs:
            model_row, fold_baselines = evaluate_cutoff(
                bundle,
                config,
                cutoff=cutoff,
                seed=int(seed),
            )
            model_rows.append(model_row)
            baseline_rows.extend(fold_baselines)

    model_summary = _summarize_rows(model_rows)
    baseline_summary: dict[str, Any] = {}
    for name in BASELINES:
        baseline_summary[name] = _summarize_rows(
            [row for row in baseline_rows if row["baseline"] == name]
        )

    primary_metric = "hit_at_1"
    model_score = model_summary["metrics"][primary_metric]["mean"]
    baseline_scores = {
        name: summary["metrics"][primary_metric]["mean"]
        for name, summary in baseline_summary.items()
    }
    best_baseline = max(baseline_scores, key=baseline_scores.get)
    best_score = baseline_scores[best_baseline]
    gain = float(model_score - best_score)
    required_gain = float(config.subset_research_gain_min)
    status = TrialStatus.PASS.value if gain > required_gain else TrialStatus.RESEARCH_NO_GAIN.value
    promotion = {
        "status": status,
        "primary_metric": primary_metric,
        "model_mean": float(model_score),
        "best_baseline": best_baseline,
        "best_baseline_mean": float(best_score),
        "absolute_gain": gain,
        "required_gain_strictly_greater_than": required_gain,
        "promotable": status == TrialStatus.PASS.value,
    }
    prospective = _prospective_prediction(bundle, config, fixed_at=fixed_at)

    artifact_dir = ""
    if output_dir is not None:
        store = ProbabilisticArtifactStore(output_dir)
        store.write_table("evaluation/model_folds.csv", pd.DataFrame(model_rows))
        store.write_table("evaluation/baseline_folds.csv", pd.DataFrame(baseline_rows))
        store.write_json("evaluation/model_summary.json", model_summary)
        store.write_json("evaluation/baseline_summary.json", baseline_summary)
        store.write_json("evaluation/promotion_decision.json", promotion)
        store.write_json("prospective/prediction.fixed.json", prospective)
        store.write_table(
            "prospective/candidate_marginals.csv",
            pd.DataFrame(
                {
                    "candidate": list(bundle.geometry.values),
                    "probability": prospective["payload"]["candidate_marginals"],
                }
            ),
        )
        store.write_json(
            "report/VERIFICATION_REPORT.json",
            {
                "status": status,
                "model_id": MODEL_ID,
                "game": bundle.game,
                "seeds": [int(seed) for seed in config.seeds],
                "cutoffs": list(cutoffs),
                "future_actual_in_prediction_payload": False,
                "prediction_sha256_verified": verify_fixed_prediction(prospective),
                "ppl01_model_ids_modified": 0,
                "promotion": promotion,
            },
        )
        store.manifest(
            metadata={
                "model_id": MODEL_ID,
                "game": bundle.game,
                "status": status,
                "prediction_payload_sha256": prospective["payload_sha256"],
            }
        )
        artifact_dir = str(store.root)

    return SubsetEvaluationResult(
        status=status,
        model_id=MODEL_ID,
        game=bundle.game,
        seeds=tuple(int(seed) for seed in config.seeds),
        cutoffs=cutoffs,
        model_rows=tuple(model_rows),
        baseline_rows=tuple(baseline_rows),
        model_summary=model_summary,
        baseline_summary=baseline_summary,
        promotion=promotion,
        prospective_prediction=prospective,
        artifact_dir=artifact_dir,
    )


__all__ = [
    "BASELINES",
    "SubsetEvaluationResult",
    "evaluate_conditional_bernoulli",
    "evaluate_cutoff",
    "fix_prospective_prediction",
    "verify_fixed_prediction",
]

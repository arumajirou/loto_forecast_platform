from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.evaluation.protocol import ProtocolSpec
from loto.probabilistic.artifact_store import ProbabilisticArtifactStore
from loto.probabilistic.catalog import get_probabilistic_model_spec
from loto.probabilistic.config import execution_fingerprint
from loto.probabilistic.dataset import DatasetBundle, task_arrays
from loto.probabilistic.decision import choose_points
from loto.probabilistic.decoder import decode
from loto.probabilistic.diagnostics import diagnose_probabilities
from loto.probabilistic.backends import get_backend
from loto.probabilistic.models.reference import ReferencePosterior
from loto.probabilistic.native import NativePosterior
from loto.probabilistic.predictive import summarize_draws


@dataclass(frozen=True)
class TrialResult:
    status: str
    trial_id: str
    model_id: str
    family: str
    game: str
    target_mode: str
    backend: str
    protocol_hash: str
    execution_fingerprint: str
    metrics: dict[str, float]
    diagnostics: dict[str, Any]
    point_prediction: list[int]
    artifact_dir: str
    elapsed_seconds: float
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "trial_id": self.trial_id,
            "model_id": self.model_id,
            "family": self.family,
            "game": self.game,
            "target_mode": self.target_mode,
            "backend": self.backend,
            "protocol_hash": self.protocol_hash,
            "execution_fingerprint": self.execution_fingerprint,
            "metrics": self.metrics,
            "diagnostics": self.diagnostics,
            "point_prediction": self.point_prediction,
            "artifact_dir": self.artifact_dir,
            "elapsed_seconds": self.elapsed_seconds,
            "error": self.error,
        }


def _protocol(bundle: DatasetBundle, *, target_mode: str, train_rows: int, test_size: int, seed: int) -> ProtocolSpec:
    return ProtocolSpec(
        game=bundle.game,
        family=bundle.geometry.family,
        positions=bundle.geometry.positions,
        universe_size=bundle.geometry.universe_size,
        target_mode=target_mode,
        horizon=1,
        data_version=bundle.data_version,
        development_rows=train_rows,
        holdout_rows=test_size,
        folds=1,
        test_size=test_size,
        min_train_size=train_rows,
        objective_primary="hit_at_1",
        seeds=(seed,),
        metric_set=("hit_at_1", "mae", "mse", "exact", "brier", "log_loss"),
        objective_weights={"hit_at_1": 1.0},
        feature_windows=(),
    )


def _normalize_probabilities(probabilities: np.ndarray, bundle: DatasetBundle, target_mode: str) -> np.ndarray:
    probs = np.asarray(probabilities, dtype=float)
    geometry = bundle.geometry
    if geometry.family == "digits" and probs.shape[0] == 1:
        probs = np.repeat(probs, geometry.positions, axis=0)
    if geometry.family == "select" and target_mode in {"select_candidate_inclusion", "window_count"}:
        if probs.shape[0] != 1:
            probs = probs.mean(axis=0, keepdims=True)
    if geometry.family == "select" and target_mode == "select_position_inclusion" and probs.shape[0] != geometry.positions:
        probs = np.repeat(probs.mean(axis=0, keepdims=True), geometry.positions, axis=0)
    probs = np.maximum(probs, 1e-15)
    probs /= probs.sum(axis=-1, keepdims=True)
    return probs


def _one_hot(actual: np.ndarray, classes: int) -> np.ndarray:
    out = np.zeros((len(actual), classes), dtype=float)
    out[np.arange(len(actual)), actual.astype(int)] = 1.0
    return out


def evaluate(
    *, actual: np.ndarray, predicted: list[int], probabilities: np.ndarray, bundle: DatasetBundle
) -> dict[str, float]:
    geometry = bundle.geometry
    actual_values = actual.astype(int)
    pred_values = np.asarray(predicted, dtype=int)
    if geometry.family == "digits":
        errors = np.abs(actual_values - pred_values)
        zero_actual = actual_values - geometry.value_min
        aligned = probabilities
        one_hot = _one_hot(zero_actual, geometry.universe_size)
        brier = float(np.mean(np.sum((aligned - one_hot) ** 2, axis=1)))
        picked = aligned[np.arange(geometry.positions), zero_actual]
        return {
            "hit_at_1": float(np.mean(errors <= 1)),
            "mae": float(np.mean(errors)),
            "mse": float(np.mean(errors**2)),
            "exact": float(np.mean(errors == 0)),
            "all_positions_within_1": float(np.all(errors <= 1)),
            "brier": brier,
            "log_loss": float(-np.mean(np.log(np.maximum(picked, 1e-15)))),
        }
    actual_set = set(actual_values.tolist())
    predicted_set = set(pred_values.tolist())
    overlap = len(actual_set & predicted_set)
    errors = np.abs(np.sort(actual_values) - np.sort(pred_values))
    if probabilities.shape[0] == 1:
        inclusion = np.zeros(geometry.universe_size, dtype=float)
        inclusion[actual_values - geometry.value_min] = 1.0
        # Scale marginal simplex to expected inclusion mass for a comparable Brier-like score.
        marginals = np.clip(probabilities[0] * geometry.positions, 0.0, 1.0)
        brier = float(np.mean((marginals - inclusion) ** 2))
        picked = probabilities[0, actual_values - geometry.value_min]
    else:
        zero_actual = actual_values - geometry.value_min
        one_hot = _one_hot(zero_actual, geometry.universe_size)
        brier = float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1)))
        picked = probabilities[np.arange(geometry.positions), zero_actual]
    return {
        "hit_at_1": float(np.mean(errors <= 1)),
        "mae": float(np.mean(errors)),
        "mse": float(np.mean(errors**2)),
        "exact": float(actual_set == predicted_set),
        "set_overlap": float(overlap),
        "jaccard": float(overlap / len(actual_set | predicted_set)),
        "brier": brier,
        "log_loss": float(-np.mean(np.log(np.maximum(picked, 1e-15)))),
    }


def _merge_native_diagnostics(
    posterior: NativePosterior,
    *,
    mean: np.ndarray,
    decoded: list[int],
    inference_profile_id: str | None,
) -> dict[str, Any]:
    probability_report = diagnose_probabilities(
        mean,
        backend=posterior.backend,
        inference_profile_id=inference_profile_id,
        point_predictions=decoded,
    ).model_dump()
    native = dict(posterior.diagnostics or {})
    for key in (
        "rhat_max",
        "ess_bulk_min",
        "ess_tail_min",
        "divergences",
        "max_treedepth_hits",
        "ebfmi_min",
        "elbo_finite",
        "elbo_stable",
        "effective_sample_size",
    ):
        if native.get(key) is not None:
            probability_report[key] = native[key]
    warnings = list(dict.fromkeys([*probability_report.get("warnings", []), *native.get("warnings", [])]))
    failures = list(
        dict.fromkeys([*probability_report.get("failure_codes", []), *native.get("failure_codes", [])])
    )
    rhat = probability_report.get("rhat_max")
    divergences = probability_report.get("divergences")
    if rhat is not None and float(rhat) > 1.05:
        warnings.append("RHAT_ABOVE_1_05")
    if divergences is not None and int(divergences) > 0:
        failures.append("MCMC_DIVERGENCES")
    if probability_report.get("elbo_finite") is False:
        failures.append("ELBO_NONFINITE")
    probability_report["warnings"] = list(dict.fromkeys(warnings))
    probability_report["failure_codes"] = list(dict.fromkeys(failures))
    if failures:
        probability_report["status"] = "FAIL"
    elif warnings:
        probability_report["status"] = "WARN"
    return probability_report


def _fit_predict_once(
    *,
    model_id: str,
    bundle: DatasetBundle,
    target_mode: str,
    backend_name: str,
    inference_profile_id: str | None,
    config,
    train_end: int,
    seed: int,
    protocol_hash: str,
    fingerprint: str,
) -> tuple[NativePosterior, np.ndarray, pd.DataFrame, list[int], dict[str, float], dict[str, Any]]:
    spec = get_probabilistic_model_spec(model_id)
    y, classes = task_arrays(bundle, target_mode)
    train = y[:train_end]
    posterior = get_backend(backend_name).execute(
        spec,
        y=train,
        classes=classes,
        target_mode=target_mode,
        geometry=bundle.geometry,
        config=config,
        seed=seed,
        inference_profile_id=inference_profile_id,
    )
    draws = posterior.probability_draws
    draw_id = bundle.draw_ids[train_end] if train_end < bundle.rows else f"next-{bundle.rows + 1}"
    mean, summary = summarize_draws(
        draws,
        model_id=model_id,
        game=bundle.game,
        target_mode=target_mode,
        draw_id=draw_id,
        geometry=bundle.geometry,
        protocol_hash=protocol_hash,
        execution_fingerprint=fingerprint,
    )
    mean = _normalize_probabilities(mean, bundle, target_mode)
    points = choose_points(
        mean,
        model_id=model_id,
        value_min=bundle.geometry.value_min,
        lambda_mse=config.utility_lambda_mse,
    )
    decoded = decode(mean, bundle.geometry, points)
    diagnostics = _merge_native_diagnostics(
        posterior,
        mean=mean,
        decoded=decoded,
        inference_profile_id=inference_profile_id,
    )
    metrics: dict[str, float] = {}
    if train_end < bundle.rows:
        metrics = evaluate(
            actual=bundle.values[train_end],
            predicted=decoded,
            probabilities=mean,
            bundle=bundle,
        )
    return posterior, mean, summary, decoded, metrics, diagnostics


def run_trial(
    *,
    trial,
    bundle: DatasetBundle,
    config,
    output_dir: str | Path,
) -> TrialResult:
    started = time.perf_counter()
    spec = get_probabilistic_model_spec(trial.model_id)
    train_rows = max(config.min_train_size, bundle.rows - config.test_size)
    train_rows = min(train_rows, bundle.rows - 1)
    test_size = min(config.test_size, bundle.rows - train_rows)
    protocol = _protocol(
        bundle, target_mode=trial.target_mode, train_rows=train_rows, test_size=test_size, seed=trial.seed
    )
    fingerprints = execution_fingerprint(
        protocol_hash=protocol.hash,
        model_spec=spec,
        run_config=config,
        backend=trial.backend,
        inference_profile_id=trial.inference_profile_id,
    )
    store = ProbabilisticArtifactStore(Path(output_dir) / "models" / trial.trial_id)
    try:
        prediction_rows: list[dict[str, Any]] = []
        metric_rows: list[dict[str, float]] = []
        last: tuple[NativePosterior, np.ndarray, pd.DataFrame, list[int], dict[str, float], dict[str, Any]] | None = None
        for cutoff in range(train_rows, train_rows + test_size):
            last = _fit_predict_once(
                model_id=trial.model_id,
                bundle=bundle,
                target_mode=trial.target_mode,
                backend_name=trial.backend,
                inference_profile_id=trial.inference_profile_id,
                config=config,
                train_end=cutoff,
                seed=trial.seed,
                protocol_hash=protocol.hash,
                fingerprint=fingerprints["execution_fingerprint"],
            )
            _, _, _, decoded, metrics, _ = last
            prediction_rows.append(
                {
                    "cutoff": cutoff,
                    "draw_id": bundle.draw_ids[cutoff],
                    "actual": json.dumps(bundle.values[cutoff].tolist()),
                    "prediction": json.dumps(decoded),
                    **metrics,
                }
            )
            metric_rows.append(metrics)
        # Refit on all observations for the next registered forecast.
        final = _fit_predict_once(
            model_id=trial.model_id,
            bundle=bundle,
            target_mode=trial.target_mode,
            backend_name=trial.backend,
            inference_profile_id=trial.inference_profile_id,
            config=config,
            train_end=bundle.rows,
            seed=trial.seed,
            protocol_hash=protocol.hash,
            fingerprint=fingerprints["execution_fingerprint"],
        )
        posterior, mean, summary, decoded, _, diagnostics = final
        aggregated = {
            key: float(np.mean([row[key] for row in metric_rows]))
            for key in metric_rows[0]
        } if metric_rows else {}
        store.write_json("model_spec.json", spec.to_dict())
        store.write_json("protocol.json", protocol.summary())
        store.write_json("execution_fingerprint.json", fingerprints)
        store.write_json("posterior_metadata.json", posterior.to_metadata_dict())
        posterior.save(store.root, save_draws=config.save_posterior_draws)
        if isinstance(posterior.native_payload, ReferencePosterior):
            store.write_json("posterior_reference.json", posterior.native_payload.to_dict())
        store.write_table("posterior_summary.csv", summary)
        store.write_table("rolling_predictions.csv", pd.DataFrame(prediction_rows))
        store.write_json("next_prediction.json", {"values": decoded, "probabilities": mean.tolist()})
        store.write_json("diagnostics.json", diagnostics)
        result = TrialResult(
            status="PASS" if diagnostics["status"] != "FAIL" else "POSTERIOR_INVALID",
            trial_id=trial.trial_id,
            model_id=trial.model_id,
            family=trial.family,
            game=trial.game,
            target_mode=trial.target_mode,
            backend=trial.backend,
            protocol_hash=protocol.hash,
            execution_fingerprint=fingerprints["execution_fingerprint"],
            metrics=aggregated,
            diagnostics=diagnostics,
            point_prediction=decoded,
            artifact_dir=str(store.root),
            elapsed_seconds=time.perf_counter() - started,
        )
        store.write_json("lifecycle_result.json", result.to_dict())
        store.manifest(metadata={"trial_id": trial.trial_id, "status": result.status})
        return result
    except Exception as exc:
        result = TrialResult(
            status="MODEL_BUILD_FAILED" if isinstance(exc, (ValueError, NotImplementedError)) else "INFERENCE_FAILED",
            trial_id=trial.trial_id,
            model_id=trial.model_id,
            family=trial.family,
            game=trial.game,
            target_mode=trial.target_mode,
            backend=trial.backend,
            protocol_hash=protocol.hash,
            execution_fingerprint=fingerprints["execution_fingerprint"],
            metrics={},
            diagnostics={},
            point_prediction=[],
            artifact_dir=str(store.root),
            elapsed_seconds=time.perf_counter() - started,
            error=f"{type(exc).__name__}: {exc}",
        )
        store.write_json("lifecycle_result.json", result.to_dict())
        store.manifest(metadata={"trial_id": trial.trial_id, "status": result.status})
        return result


def load_reference_posterior(path: str | Path) -> ReferencePosterior:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ReferencePosterior.from_dict(payload)

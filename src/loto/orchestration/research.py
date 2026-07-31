from __future__ import annotations

import json
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.data.canonical import canonicalize_loto7
from loto.data.lineage import atomic_write_json
from loto.decoding.hybrid import decode_hybrid
from loto.evaluation.detailed_metrics import (
    candidate_ranking_metrics,
    composite_score,
    detailed_draw_metrics,
    expected_calibration_error,
)
from loto.evaluation.metrics import brier_score, log_loss
from loto.evaluation.splits import rolling_folds, split_development_holdout
from loto.experiment_config import ExperimentConfig
from loto.features.pipeline import build_candidate_features, build_next_candidate_features
from loto.models.catalog import get_model_spec
from loto.models.factory import RuntimeModel, WorkerGateway
from loto.models.position import PositionFrequencyAdapter
from loto.models.workers import PositionSeriesWorker
from loto.notifications import NotificationSender, build_run_summary, write_notification_report
from loto.observability.gpu import collect_gpu_evidence
from loto.observability.metrics import observe_trial
from loto.observability.mlflow_bridge import MlflowBridge
from loto.observability.runtime import JsonEventLogger, ResourceMonitor
from loto.observability.tracing import TraceManager
from loto.optimization.search import PARAM_SPACES, optimize_optuna, optimize_ray


def _targets(numbers: list[int]) -> np.ndarray:
    values = np.zeros(37, dtype=float)
    values[np.asarray(numbers, dtype=int) - 1] = 1.0
    return values


def _rank_to_combo(probabilities: np.ndarray, position_matrix: np.ndarray) -> list[int]:
    combinations = decode_hybrid(np.asarray(probabilities, dtype=float), position_matrix, top_k=1)
    return combinations[0].numbers


def _candidate_fold(
    master: pd.DataFrame,
    model_id: str,
    params: dict[str, Any],
    seed: int,
    train_end: int,
    test_start: int,
    test_end: int,
    windows: tuple[int, ...],
) -> tuple[list[list[int]], list[np.ndarray], list[list[int]], list[dict[str, Any]]]:
    predictions: list[list[int]] = []
    probabilities: list[np.ndarray] = []
    actuals: list[list[int]] = []
    resources: list[dict[str, Any]] = []
    spec = get_model_spec(model_id)
    for draw_index in range(test_start, test_end):
        history = master.iloc[:draw_index].copy()
        train_features = build_candidate_features(history, windows=windows)
        query = build_next_candidate_features(history, windows=windows)
        before = collect_gpu_evidence(gpu_required=False)
        started = time.perf_counter()
        runtime = RuntimeModel(spec, params, seed=seed).fit_candidate(train_features)
        output = runtime.predict_candidate(query)
        elapsed = time.perf_counter() - started
        after = collect_gpu_evidence(gpu_required=False)
        probability = np.clip(
            np.asarray(output.candidate_probabilities, dtype=float), 1e-9, 1 - 1e-9
        )
        position = PositionFrequencyAdapter().fit(history).predict_matrix()
        predicted = _rank_to_combo(probability, position)
        row = master.iloc[draw_index]
        actual = [int(row[f"n{i}"]) for i in range(1, 8)]
        predictions.append(predicted)
        probabilities.append(probability)
        actuals.append(actual)
        resources.append(
            {"draw_index": draw_index, "elapsed_seconds": elapsed, "before": before, "after": after}
        )
    return predictions, probabilities, actuals, resources


def _position_fold(
    master: pd.DataFrame,
    model_id: str,
    params: dict[str, Any],
    seed: int,
    test_start: int,
    test_end: int,
    device: str,
    precision: str,
) -> tuple[list[list[int]], list[np.ndarray], list[list[int]], list[dict[str, Any]]]:
    predictions: list[list[int]] = []
    probabilities: list[np.ndarray] = []
    actuals: list[list[int]] = []
    resources: list[dict[str, Any]] = []
    spec = get_model_spec(model_id)
    gpu_required = device == "cuda" and "gpu" in spec.capabilities
    for draw_index in range(test_start, test_end):
        history = master.iloc[:draw_index].copy()
        before = collect_gpu_evidence(gpu_required=False)
        started = time.perf_counter()
        output = PositionSeriesWorker(
            spec, params, seed=seed, device=device, precision=precision
        ).forecast(history)
        elapsed = time.perf_counter() - started
        after = collect_gpu_evidence(gpu_required=gpu_required)
        values = np.clip(np.rint(output.position_values), 1, 37).astype(int)
        values = np.sort(values)
        for index in range(1, 7):
            if values[index] <= values[index - 1]:
                values[index] = values[index - 1] + 1
        if values[-1] > 37:
            values = np.arange(31, 38)
        actual_row = master.iloc[draw_index]
        actual = [int(actual_row[f"n{i}"]) for i in range(1, 8)]
        predictions.append(values.tolist())
        probabilities.append(np.asarray(output.candidate_probabilities, dtype=float))
        actuals.append(actual)
        resources.append(
            {
                "draw_index": draw_index,
                "elapsed_seconds": elapsed,
                "before": before,
                "after": after,
                "worker": output.metadata,
                "gpu_certification": "VERIFIED"
                if after.get("eligible") and gpu_required
                else "NOT_REQUIRED"
                if not gpu_required
                else "PARTIAL",
            }
        )
    return predictions, probabilities, actuals, resources


def _metric_bundle(
    actual: list[list[int]], predicted: list[list[int]], probs: list[np.ndarray]
) -> dict[str, Any]:
    targets = np.asarray([_targets(row) for row in actual])
    matrix = np.asarray(probs, dtype=float)
    result = detailed_draw_metrics(np.asarray(actual), np.asarray(predicted))
    result.update(
        {
            "brier": brier_score(targets, matrix),
            "log_loss": log_loss(targets, matrix),
            "ece": expected_calibration_error(targets, matrix),
            **candidate_ranking_metrics(targets, matrix, k=7),
        }
    )
    return result


def _tune_candidate_params(
    master: pd.DataFrame,
    model_id: str,
    base_params: dict[str, Any],
    seed: int,
    train_end: int,
    config: ExperimentConfig,
    windows: tuple[int, ...],
    output: Path,
) -> dict[str, Any]:
    if config.search.backend == "none" or model_id not in PARAM_SPACES:
        return base_params
    inner = rolling_folds(
        train_end,
        folds=config.cv.inner_folds,
        test_size=max(1, min(config.cv.test_size, 5)),
        min_train_size=config.cv.min_train_size,
        gap=config.cv.gap,
        expanding=config.cv.expanding,
    )
    if not inner:
        return base_params

    def objective(candidate_params: dict[str, Any]) -> float:
        rows = []
        for fold in inner:
            pred, probs, actual, _ = _candidate_fold(
                master.iloc[:train_end],
                model_id,
                base_params | candidate_params,
                seed,
                fold.train_end,
                fold.test_start,
                fold.test_end,
                windows,
            )
            metric = _metric_bundle(actual, pred, probs)
            rows.append(composite_score(metric, config.objective.weights))
        return float(np.mean(rows))

    if config.search.backend == "optuna":
        result = optimize_optuna(
            model_id,
            objective,
            trials=config.search.trials,
            timeout_seconds=config.search.timeout_seconds,
            sampler=config.search.sampler,
            pruner=config.search.pruner,
            seed=seed,
            jobs=config.search.parallel_jobs,
        )
    else:
        result = optimize_ray(
            model_id,
            objective,
            trials=config.search.trials,
            timeout_seconds=config.search.timeout_seconds,
            cpus_per_trial=config.search.cpus_per_trial,
            gpus_per_trial=config.search.gpus_per_trial,
            output_dir=str(output / "ray" / model_id),
        )
    search_dir = output / "search" / f"{model_id}-s{seed}"
    search_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        search_dir / "result.json",
        {
            "backend": result.backend,
            "best_params": result.best_params,
            "best_value": result.best_value,
            "trials": result.trials,
        },
    )
    return base_params | result.best_params


def _resume_keys(output: Path, config_hash: str) -> set[tuple[str, int]]:
    summary_path = output / "research_summary.json"
    trials_path = output / "trial_results.csv"
    if not summary_path.exists() or not trials_path.exists():
        return set()
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("config_hash") != config_hash:
            return set()
        frame = pd.read_csv(trials_path)
        return {
            (str(row.model_id), int(row.seed))
            for row in frame.itertuples()
            if row.status == "SUCCEEDED"
        }
    except Exception:
        return set()


def _write_parquet(frame: pd.DataFrame, path: Path) -> dict[str, Any]:
    try:
        frame.to_parquet(path, index=False)
        return {"status": "WRITTEN", "path": str(path), "bytes": path.stat().st_size}
    except Exception as exc:
        return {"status": "FAILED", "path": str(path), "error": f"{type(exc).__name__}: {exc}"}


def run_research_experiment(config: ExperimentConfig) -> dict[str, Any]:
    output = Path(config.runtime.output)
    output.mkdir(parents=True, exist_ok=True)
    run_id = f"research-{uuid.uuid4().hex[:12]}"
    config.write_resolved(output / "resolved_config.yaml")
    events = JsonEventLogger(output / "events.jsonl", run_id, {"config_hash": config.config_hash})
    trace = TraceManager(otlp_endpoint=config.observability.otlp_endpoint)
    monitor = ResourceMonitor(
        output / "resource_samples.jsonl", capture_gpu=config.observability.capture_gpu
    )
    monitor.start()
    events.emit("research.run", status="STARTED")
    mlflow_status: dict[str, Any] = {"enabled": False, "reason": "not_configured"}
    notification_status: list[dict[str, Any]] = []
    try:
        with trace.span("research.load_data", {"run.id": run_id}):
            raw = pd.read_csv(config.data.input)
            master, manifest = canonicalize_loto7(raw, source=config.data.input)
            development_slice, holdout_slice = split_development_holdout(
                len(master), config.cv.holdout_size
            )
            development = master.iloc[development_slice].reset_index(drop=True)
            holdout = master.iloc[holdout_slice].reset_index(drop=True)
            folds = rolling_folds(
                len(development),
                folds=config.cv.outer_folds,
                test_size=config.cv.test_size,
                min_train_size=config.cv.min_train_size,
                gap=config.cv.gap,
                expanding=config.cv.expanding,
            )
        if not folds:
            raise ValueError(
                "no outer folds can be constructed; reduce holdout/test size or min_train_size"
            )

        existing_keys = _resume_keys(output, config.config_hash) if config.runtime.resume else set()
        trials: list[dict[str, Any]] = []
        fold_rows: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        gateway = WorkerGateway()
        windows = tuple(config.data.feature_windows)
        consecutive_failures = 0

        for model_id in config.models:
            spec = get_model_spec(model_id)
            params = config.model_params.get(model_id, {})
            if not spec.available:
                failed.append(
                    {
                        "model_id": model_id,
                        "status": "UNAVAILABLE",
                        "reason": f"optional package missing: {spec.package}",
                    }
                )
                events.emit(
                    "research.model", status="UNAVAILABLE", model_id=model_id, package=spec.package
                )
                continue
            for seed in config.cv.seeds:
                trial_key = (model_id, seed)
                trial_id = f"{model_id}-s{seed}"
                if trial_key in existing_keys:
                    skipped.append(
                        {
                            "trial_id": trial_id,
                            "model_id": model_id,
                            "seed": seed,
                            "status": "RESUMED_SKIP",
                        }
                    )
                    events.emit(
                        "research.trial",
                        status="RESUMED_SKIP",
                        trial_id=trial_id,
                        model_id=model_id,
                        seed=seed,
                    )
                    continue
                model_predictions: list[list[int]] = []
                model_actuals: list[list[int]] = []
                model_probs: list[np.ndarray] = []
                elapsed_total = 0.0
                resource_rows: list[dict[str, Any]] = []
                resolved_params = dict(params)
                trial_started = time.perf_counter()
                events.emit(
                    "research.trial",
                    status="STARTED",
                    trial_id=trial_id,
                    model_id=model_id,
                    seed=seed,
                )
                try:
                    with trace.span(
                        "research.trial", {"trial.id": trial_id, "model.id": model_id, "seed": seed}
                    ):
                        for fold in folds:
                            started = time.perf_counter()
                            fold_params = params
                            if spec.task == "candidate":
                                fold_params = _tune_candidate_params(
                                    development,
                                    model_id,
                                    params,
                                    seed,
                                    fold.train_end,
                                    config,
                                    windows,
                                    output,
                                )
                                resolved_params = fold_params
                                pred, probs, actual, resources = _candidate_fold(
                                    development,
                                    model_id,
                                    fold_params,
                                    seed,
                                    fold.train_end,
                                    fold.test_start,
                                    fold.test_end,
                                    windows,
                                )
                            elif spec.task in {"position_series", "foundation"}:
                                # Foundation time-series models use the same
                                # seven-position forecasting contract and are
                                # dispatched by PositionSeriesWorker.
                                pred, probs, actual, resources = _position_fold(
                                    development,
                                    model_id,
                                    params,
                                    seed,
                                    fold.test_start,
                                    fold.test_end,
                                    config.runtime.device,
                                    config.runtime.precision,
                                )
                            else:
                                job = gateway.build_job(
                                    model_id,
                                    params=params,
                                    input_uri=config.data.input,
                                    output_uri=str(output / "worker_jobs" / trial_id),
                                    seed=seed,
                                    device=config.runtime.device,
                                    precision=config.runtime.precision,
                                )
                                gateway.write_job(job, output / "worker_jobs" / f"{trial_id}.json")
                                raise RuntimeError(
                                    f"task {spec.task} requires provider plugin/worker"
                                )
                            elapsed = time.perf_counter() - started
                            elapsed_total += elapsed
                            fold_metric = _metric_bundle(actual, pred, probs)
                            fold_metric["elapsed_seconds"] = elapsed
                            fold_rows.append(
                                {
                                    "trial_id": trial_id,
                                    "model_id": model_id,
                                    "seed": seed,
                                    "fold_id": fold.fold_id,
                                    **fold_metric,
                                }
                            )
                            for resource in resources:
                                resource_rows.append({"fold_id": fold.fold_id, **resource})
                            model_predictions.extend(pred)
                            model_actuals.extend(actual)
                            model_probs.extend(probs)
                    aggregate = _metric_bundle(model_actuals, model_predictions, model_probs)
                    aggregate["elapsed_seconds"] = elapsed_total
                    aggregate["composite_score"] = composite_score(
                        aggregate, config.objective.weights
                    )
                    row = {
                        "trial_id": trial_id,
                        "model_id": model_id,
                        "family": spec.family,
                        "library": spec.library,
                        "seed": seed,
                        "status": "SUCCEEDED",
                        "available": spec.available,
                        "params": json.dumps(spec.default_params | resolved_params, sort_keys=True),
                        **aggregate,
                    }
                    trials.append(row)
                    atomic_write_json(output / "resources" / f"{trial_id}.json", resource_rows)
                    observe_trial(
                        model_id, "SUCCEEDED", time.perf_counter() - trial_started, aggregate
                    )
                    events.emit(
                        "research.trial",
                        status="SUCCEEDED",
                        trial_id=trial_id,
                        model_id=model_id,
                        seed=seed,
                        metrics=aggregate,
                    )
                    consecutive_failures = 0
                except Exception as exc:
                    failure = {
                        "trial_id": trial_id,
                        "model_id": model_id,
                        "seed": seed,
                        "status": "FAILED",
                        "reason": str(exc),
                        "traceback": traceback.format_exc(),
                    }
                    failed.append(failure)
                    atomic_write_json(output / "failures" / f"{trial_id}.json", failure)
                    observe_trial(model_id, "FAILED", time.perf_counter() - trial_started)
                    events.emit(
                        "research.trial",
                        status="FAILED",
                        trial_id=trial_id,
                        model_id=model_id,
                        seed=seed,
                        error=str(exc),
                    )
                    consecutive_failures += 1
                    if config.search.fail_fast:
                        raise
                    if consecutive_failures >= config.search.max_consecutive_failures:
                        events.emit(
                            "research.run",
                            status="STOPPED_FAILURE_LIMIT",
                            failures=consecutive_failures,
                        )
                        break
            if consecutive_failures >= config.search.max_consecutive_failures:
                break

        trial_frame = pd.DataFrame(trials)
        fold_frame = pd.DataFrame(fold_rows)
        failed_frame = pd.DataFrame(failed)
        skipped_frame = pd.DataFrame(skipped)
        if not trial_frame.empty:
            aggregate_columns = {
                "composite_score": "mean",
                "mean_hits_at_7": "mean",
                "mean_within_1": "mean",
                "all_positions_within_1": "mean",
                "worst_position_within_1": "mean",
                "position_mae": "mean",
                "position_mse": "mean",
                "position_rmse": "mean",
                "brier": "mean",
                "log_loss": "mean",
                "ece": "mean",
                "precision_at_7": "mean",
                "recall_at_7": "mean",
                "ndcg_at_7": "mean",
                "elapsed_seconds": "sum",
            }
            leaderboard = (
                trial_frame.groupby(["model_id", "family", "library"], as_index=False)
                .agg(aggregate_columns)
                .sort_values(["composite_score", config.objective.primary], ascending=False)
                .reset_index(drop=True)
            )
            leaderboard.insert(0, "rank", np.arange(1, len(leaderboard) + 1))
        else:
            leaderboard = pd.DataFrame()

        trial_frame.to_csv(output / "trial_results.csv", index=False)
        fold_frame.to_csv(output / "fold_results.csv", index=False)
        failed_frame.to_csv(output / "failed_trials.csv", index=False)
        skipped_frame.to_csv(output / "skipped_trials.csv", index=False)
        leaderboard.to_csv(output / "model_leaderboard.csv", index=False)
        artifact_status = {
            "trial_results.parquet": _write_parquet(trial_frame, output / "trial_results.parquet"),
            "fold_results.parquet": _write_parquet(fold_frame, output / "fold_results.parquet"),
        }
        atomic_write_json(output / "artifact_status.json", artifact_status)
        catalog = [get_model_spec(model_id).to_dict() for model_id in config.models]
        atomic_write_json(output / "model_availability.json", catalog)
        summary: dict[str, Any] = {
            "schema_version": "2.1.0",
            "run_id": run_id,
            "status": "SUCCEEDED" if trials and not failed else "PARTIAL" if trials else "FAILED",
            "config_hash": config.config_hash,
            "data_version": manifest.data_version,
            "development_draws": len(development),
            "holdout_draws": len(holdout),
            "outer_folds": [fold.__dict__ for fold in folds],
            "successful_trials": len(trials),
            "failed_trials": len(failed),
            "skipped_trials": len(skipped),
            "champion": None if leaderboard.empty else leaderboard.iloc[0].to_dict(),
            "holdout_evaluated": False,
            "artifact_status": artifact_status,
            "events": str(output / "events.jsonl"),
            "resource_samples": str(output / "resource_samples.jsonl"),
            "note": "Holdout remains untouched until an explicit certification command.",
        }
        atomic_write_json(output / "research_summary.json", summary)
        if config.observability.mlflow_uri:
            metrics = {
                "successful_trials": float(len(trials)),
                "failed_trials": float(len(failed)),
            }
            if summary["champion"]:
                for key in (
                    "composite_score",
                    "mean_hits_at_7",
                    "mean_within_1",
                    "position_mae",
                    "position_mse",
                    "brier",
                    "ece",
                ):
                    if key in summary["champion"]:
                        metrics[f"champion_{key}"] = float(summary["champion"][key])
            mlflow_status = MlflowBridge(
                config.observability.mlflow_uri, config.observability.experiment_name
            ).record_run(
                run_id,
                {
                    "config_hash": config.config_hash,
                    "models": config.models,
                    "data_version": manifest.data_version,
                },
                metrics,
                [
                    output / "research_summary.json",
                    output / "model_leaderboard.csv",
                    output / "resolved_config.yaml",
                ],
            )
            atomic_write_json(output / "mlflow_status.json", mlflow_status)
            summary["mlflow"] = mlflow_status
        notify_summary = build_run_summary(summary, output_dir=output)
        notify_results = NotificationSender(base_dir=output).send_all(notify_summary)
        notification_status = [item.to_dict() for item in notify_results]
        write_notification_report(notify_results, output / "notification_status.json")
        summary["notifications"] = notification_status
        atomic_write_json(output / "research_summary.json", summary)
        events.emit(
            "research.run",
            status=summary["status"],
            successful_trials=len(trials),
            failed_trials=len(failed),
        )
        return summary
    except Exception as exc:
        events.emit("research.run", status="FAILED", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        monitor.stop()

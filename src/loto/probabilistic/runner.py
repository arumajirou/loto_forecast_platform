from __future__ import annotations

import json
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

import pandas as pd

from loto.probabilistic.artifact_store import ProbabilisticArtifactStore
from loto.probabilistic.catalog import catalog_counts
from loto.probabilistic.config import environment_fingerprint, stable_hash
from loto.probabilistic.contracts import ProbabilisticRunConfig
from loto.probabilistic.dataset import DatasetBundle, load_dataset, synthetic_dataset
from loto.probabilistic.lifecycle import TrialResult, run_trial
from loto.probabilistic.notifications import (
    NotificationManager,
    NotificationSettings,
    progress_message,
)
from loto.probabilistic.planner import build_plan, plan_summary
from loto.probabilistic.progress import ProgressEstimator, gpu_snapshot
from loto.probabilistic.resources import (
    ProbabilisticResourcePolicy,
    ProbabilisticResourceScheduler,
    ResourceAwareDispatcher,
)


def _run_id(config: ProbabilisticRunConfig) -> str:
    if config.run_id:
        return config.run_id
    return time.strftime("ppl-%Y%m%d-%H%M%S") + "-" + stable_hash(config.model_dump())[:8]


def _bundles(config: ProbabilisticRunConfig) -> dict[str, DatasetBundle]:
    output: dict[str, DatasetBundle] = {}
    for index, game in enumerate(config.games):
        if game in config.inputs:
            output[game] = load_dataset(config.inputs[game], game)
        else:
            output[game] = synthetic_dataset(
                game,
                rows=config.synthetic_rows,
                seed=config.seeds[0] + index * 1009,
            )
    return output


def _blocked_result(trial: Any, run_dir: Path) -> dict[str, Any]:
    return {
        "status": "BLOCKED",
        "trial_id": trial.trial_id,
        "model_id": trial.model_id,
        "family": trial.family,
        "game": trial.game,
        "target_mode": trial.target_mode,
        "backend": trial.backend,
        "reason_code": trial.reason_code,
        "details": list(trial.details),
        "artifact_dir": str(run_dir / "models" / trial.trial_id),
    }


def _leaderboards(results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    passed = [row for row in results if row.get("status") == "PASS" and row.get("metrics")]
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in passed:
        key = str(row.get("protocol_hash", ""))
        groups.setdefault(key, []).append(row)
    output: dict[str, list[dict[str, Any]]] = {}
    for protocol_hash, rows in groups.items():
        ordered = sorted(
            rows,
            key=lambda row: (
                -float(row["metrics"].get("hit_at_1", -1.0)),
                float(row["metrics"].get("mae", float("inf"))),
                float(row["metrics"].get("mse", float("inf"))),
                row["model_id"],
            ),
        )
        output[protocol_hash] = [
            {
                "rank": rank,
                "model_id": row["model_id"],
                "family": row["family"],
                "game": row["game"],
                "target_mode": row["target_mode"],
                "backend": row["backend"],
                **row["metrics"],
            }
            for rank, row in enumerate(ordered, 1)
        ]
    return output


def _read_status_files(run_dir: Path) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    status_dir = run_dir / "status"
    if not status_dir.is_dir():
        return output
    for path in sorted(status_dir.glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        trial_id = str(row.get("trial_id") or path.stem)
        output[trial_id] = row
    return output


def _best_result(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [row for row in results if row.get("status") == "PASS" and row.get("metrics")]
    if not candidates:
        return None
    row = min(
        candidates,
        key=lambda item: (
            -float((item.get("metrics") or {}).get("hit_at_1", -1.0)),
            float((item.get("metrics") or {}).get("mae", float("inf"))),
            float((item.get("metrics") or {}).get("mse", float("inf"))),
            str(item.get("model_id")),
        ),
    )
    metrics = row.get("metrics") or {}
    return {
        "model_id": row.get("model_id"),
        "game": row.get("game"),
        "hit_at_1": metrics.get("hit_at_1"),
        "mae": metrics.get("mae"),
        "mse": metrics.get("mse"),
    }


def _status_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row.get("status", "UNKNOWN")) for row in results)
    return dict(sorted(counts.items()))


def _progress_payload(
    *,
    run_id: str,
    run_dir: Path,
    started_at: float,
    allowed_total: int,
    blocked_total: int,
    completed_results: list[dict[str, Any]],
    running_trials: list[str],
    pending_by_resource: dict[str, int],
    running_by_resource: dict[str, int],
    status: str,
    eta: dict[str, Any] | None = None,
    parallelism: dict[str, Any] | None = None,
    gpu: dict[str, Any] | None = None,
) -> dict[str, Any]:
    allowed_results = [row for row in completed_results if row.get("status") != "BLOCKED"]
    completed_allowed = len(allowed_results)
    return {
        "schema_version": 1,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "status": status,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "elapsed_seconds": round(time.monotonic() - started_at, 1),
        "trials_allowed": allowed_total,
        "trials_blocked": blocked_total,
        "completed_allowed": completed_allowed,
        "remaining_allowed": max(allowed_total - completed_allowed, 0),
        "progress_percent": round(
            completed_allowed / allowed_total * 100.0 if allowed_total else 100.0,
            2,
        ),
        "status_counts": _status_counts(completed_results),
        "running_trials": sorted(running_trials),
        "pending_by_resource": pending_by_resource,
        "running_by_resource": running_by_resource,
        "best_model": _best_result(completed_results),
        "eta": eta or {},
        "parallelism": parallelism or {},
        "gpu": gpu or {},
    }


def _write_final_artifacts(
    store: ProbabilisticArtifactStore,
    run_dir: Path,
    run_id: str,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    results.sort(key=lambda row: str(row.get("trial_id")))
    store.write_json("results.json", results)
    flat_rows = []
    for row in results:
        flat_rows.append(
            {
                "status": row.get("status"),
                "trial_id": row.get("trial_id"),
                "model_id": row.get("model_id"),
                "family": row.get("family"),
                "game": row.get("game"),
                "target_mode": row.get("target_mode"),
                "backend": row.get("backend"),
                "protocol_hash": row.get("protocol_hash"),
                "elapsed_seconds": row.get("elapsed_seconds"),
                **(row.get("metrics") or {}),
                "error": row.get("error"),
            }
        )
    store.write_table("results.csv", pd.DataFrame(flat_rows))
    leaderboards = _leaderboards(results)
    store.write_json("comparison/leaderboards.json", leaderboards)
    for protocol_hash, rows in leaderboards.items():
        store.write_table(
            f"comparison/leaderboard-{protocol_hash[:12]}.csv",
            pd.DataFrame(rows),
        )
    counts = _status_counts(results)
    overall = (
        "PASS"
        if counts.get("PASS", 0) == len(results)
        else ("PARTIAL" if counts.get("PASS", 0) else "FAILED")
    )
    report = {
        "status": overall,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "models_planned": len({row.get("model_id") for row in results}),
        "trials_total": len(results),
        "status_counts": counts,
        "protocol_groups": len(leaderboards),
        "leaderboard_paths": sorted(
            str(path.relative_to(run_dir)) for path in (run_dir / "comparison").glob("*.csv")
        ),
    }
    store.write_json("report/summary.json", report)
    store.manifest(metadata={"run_id": run_id, "status": overall})
    return report


def run_probabilistic(config: ProbabilisticRunConfig) -> dict[str, Any]:
    started_at = time.monotonic()
    run_id = _run_id(config)
    run_dir = Path(config.output).resolve() / run_id
    store = ProbabilisticArtifactStore(run_dir)
    plans = build_plan(config)
    summary = plan_summary(config)
    existing = _read_status_files(run_dir)

    if existing and config.resume_policy == "disabled":
        raise RuntimeError(
            f"run directory already contains {len(existing)} status files: {run_dir}; "
            "set resume_policy to skip_completed/skip_pass or choose a new run_id"
        )

    if existing:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        store.write_yaml(f"resume/run_config-{stamp}.yaml", config.model_dump(mode="json"))
    else:
        store.write_yaml("run_config.yaml", config.model_dump(mode="json"))
    store.write_json("plan.json", summary)
    store.write_json("environment.json", environment_fingerprint())
    store.write_json("catalog_counts.json", catalog_counts())

    if config.dry_run:
        store.manifest(metadata={"status": "DRY_RUN", "run_id": run_id})
        return {"status": "DRY_RUN", "run_id": run_id, "run_dir": str(run_dir), **summary}

    bundles = _bundles(config)
    for game, bundle in bundles.items():
        store.write_json(
            f"datasets/{game}.json",
            {
                "game": game,
                "rows": bundle.rows,
                "data_version": bundle.data_version,
                "feature_set_hash": bundle.feature_set_hash,
                "geometry": bundle.geometry.to_dict(),
                "source": config.inputs.get(game, "synthetic"),
            },
        )

    policy = ProbabilisticResourcePolicy(
        outer_workers=config.outer_workers,
        max_heavy_cpu_jobs=config.max_heavy_cpu_jobs,
        max_gpu_jobs=config.max_gpu_jobs,
        gpu_priority=config.gpu_priority,
        gpu_backends=tuple(config.gpu_backends),
        native_device=config.native_device,
    )
    legacy_scheduler = ProbabilisticResourceScheduler(policy)
    blocked = [_blocked_result(trial, run_dir) for trial in plans if not trial.allowed]
    plan_by_id = {trial.trial_id: trial for trial in plans}

    skip_ids: set[str] = set()
    retained_existing: list[dict[str, Any]] = []
    if config.resume_policy == "skip_completed":
        skip_ids = set(existing)
        retained_existing = list(existing.values())
    elif config.resume_policy == "skip_pass":
        skip_ids = {trial_id for trial_id, row in existing.items() if row.get("status") == "PASS"}
        retained_existing = [existing[trial_id] for trial_id in sorted(skip_ids)]

    results: list[dict[str, Any]] = [*blocked, *retained_existing]
    allowed_all = [trial for trial in plans if trial.allowed]
    allowed = [trial for trial in allowed_all if trial.trial_id not in skip_ids]
    dispatcher = ResourceAwareDispatcher(policy, allowed)
    estimator = ProgressEstimator(
        outer_workers=config.outer_workers,
        limits={
            "gpu": max(config.max_gpu_jobs, 1),
            "heavy_cpu": max(config.max_heavy_cpu_jobs, 1),
            "light_cpu": config.outer_workers,
        },
        defaults={
            "gpu": config.eta_default_gpu_seconds,
            "heavy_cpu": config.eta_default_heavy_cpu_seconds,
            "light_cpu": config.eta_default_light_cpu_seconds,
        },
    )
    for row in retained_existing:
        trial = plan_by_id.get(str(row.get("trial_id")))
        resource = (
            policy.effective_resource(trial)
            if trial is not None
            else str(row.get("resource_class") or "light_cpu")
        )
        elapsed = row.get("elapsed_seconds")
        if elapsed is not None:
            estimator.durations[resource].append(float(elapsed))

    notifier = NotificationManager(
        NotificationSettings.from_config(config),
        run_dir / "notifications" / "events.jsonl",
    )

    pool = ThreadPoolExecutor(
        max_workers=config.outer_workers,
        thread_name_prefix="loto-ppl",
    )
    future_map: dict[Future[TrialResult], tuple[Any, str]] = {}
    last_progress_write = 0.0
    last_time_notification = time.monotonic()
    last_notified_completed = len(retained_existing)

    def current_progress(status: str) -> dict[str, Any]:
        running_resources = {trial.trial_id: resource for trial, resource in future_map.values()}
        eta = estimator.estimate(
            dispatcher.pending_by_resource(),
            running_resources,
        )
        payload = _progress_payload(
            run_id=run_id,
            run_dir=run_dir,
            started_at=started_at,
            allowed_total=len(allowed_all),
            blocked_total=len(blocked),
            completed_results=results,
            running_trials=list(running_resources),
            pending_by_resource=dispatcher.pending_by_resource(),
            running_by_resource=dispatcher.running_by_resource(),
            status=status,
            eta=eta,
            parallelism=dispatcher.audit(),
            gpu=gpu_snapshot(),
        )
        store.write_json("report/progress.json", payload)
        store.write_json("report/parallelism_audit.json", payload["parallelism"])
        return payload

    initial_progress = current_progress("RUNNING")
    start_subject, start_body = progress_message(initial_progress)
    if config.email_on_start:
        notifier.email(start_subject.replace("完了", "開始"), start_body)
    notifier.speak(
        f"確率モデル実行を開始します。対象は{len(allowed_all)}件、"
        f"再開済みは{len(retained_existing)}件です。",
        force=True,
    )

    def execute(trial: Any, resource: str) -> TrialResult:
        if config.scheduling_policy == "legacy":
            with legacy_scheduler.lease(resource):
                return run_trial(
                    trial=trial,
                    bundle=bundles[trial.game],
                    config=config,
                    output_dir=run_dir,
                )
        return run_trial(
            trial=trial,
            bundle=bundles[trial.game],
            config=config,
            output_dir=run_dir,
        )

    try:
        while dispatcher.pending_count() or future_map:
            while len(future_map) < config.outer_workers:
                trial = dispatcher.pop_ready()
                if trial is None:
                    break
                resource = dispatcher.resource_for(trial)
                estimator.start(trial.trial_id, resource)
                future_map[pool.submit(execute, trial, resource)] = (trial, resource)

            now = time.monotonic()
            if now - last_progress_write >= config.progress_write_interval_seconds:
                current_progress("RUNNING")
                last_progress_write = now

            if not future_map:
                if dispatcher.pending_count():
                    raise RuntimeError(
                        "scheduler deadlock: pending trials exist but none can be submitted; "
                        f"pending={dispatcher.pending_by_resource()}"
                    )
                break

            done, _ = wait(
                tuple(future_map),
                timeout=min(float(config.progress_write_interval_seconds), 2.0),
                return_when=FIRST_COMPLETED,
            )
            if not done:
                if now - last_time_notification >= config.notify_progress_seconds:
                    progress = current_progress("RUNNING")
                    subject, body = progress_message(progress)
                    if config.email_on_progress:
                        notifier.email(subject, body)
                    eta_text = (progress.get("eta") or {}).get("estimated_remaining_text", "不明")
                    notifier.speak(
                        f"進捗は{progress['completed_allowed']}件中{len(allowed_all)}件、"
                        f"{progress['progress_percent']}パーセントです。"
                        f"残り予測は{eta_text}です。"
                    )
                    last_time_notification = now
                continue

            for future in done:
                trial, resource = future_map.pop(future)
                dispatcher.release(resource)
                try:
                    result = future.result().to_dict()
                except Exception as exc:
                    result = {
                        "status": "INFERENCE_FAILED",
                        "trial_id": trial.trial_id,
                        "model_id": trial.model_id,
                        "family": trial.family,
                        "game": trial.game,
                        "target_mode": trial.target_mode,
                        "backend": trial.backend,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                result["resource_class"] = resource
                estimator.finish(
                    trial.trial_id,
                    resource,
                    result.get("elapsed_seconds"),
                )
                results = [row for row in results if row.get("trial_id") != result.get("trial_id")]
                results.append(result)
                store.write_json(f"status/{trial.trial_id}.json", result)

                completed_allowed = len([row for row in results if row.get("status") != "BLOCKED"])
                should_count_notify = (
                    completed_allowed - last_notified_completed >= config.notify_every_completed
                )
                is_failure = result.get("status") != "PASS"
                progress = current_progress("RUNNING")
                last_progress_write = time.monotonic()

                if should_count_notify or is_failure:
                    subject, body = progress_message(progress)
                    if is_failure:
                        subject = f"[LOTO PPL][{result.get('status')}] {result.get('model_id')}"
                        body = (
                            f"モデル: {result.get('model_id')}\n"
                            f"status: {result.get('status')}\n"
                            f"backend: {result.get('backend')}\n"
                            f"resource: {resource}\n"
                            f"error: {result.get('error')}\n\n{body}"
                        )
                    if (is_failure and config.email_on_failure) or (
                        should_count_notify and config.email_on_progress
                    ):
                        notifier.email(subject, body)
                    eta_text = (progress.get("eta") or {}).get("estimated_remaining_text", "不明")
                    notifier.speak(
                        f"{completed_allowed}件完了しました。"
                        f"直近のモデルは{result.get('model_id')}、"
                        f"状態は{result.get('status')}です。"
                        f"残り予測は{eta_text}です。"
                    )
                    last_notified_completed = completed_allowed
                    last_time_notification = time.monotonic()

        report = _write_final_artifacts(store, run_dir, run_id, results)
        final_progress = current_progress(report["status"])
        subject, body = progress_message(final_progress)
        subject = subject.replace("[LOTO PPL]", f"[LOTO PPL][{report['status']}]")
        if config.email_on_completion:
            notifier.email(subject, body)
        notifier.speak(
            f"確率モデル実行が終了しました。状態は{report['status']}、"
            f"パスは{report['status_counts'].get('PASS', 0)}件です。",
            force=True,
        )
        return report
    except KeyboardInterrupt:
        progress = current_progress("STOPPED_BY_USER")
        _, body = progress_message(progress)
        if config.email_on_failure:
            notifier.email("[LOTO PPL] ユーザー操作により停止", body)
        notifier.speak(
            "確率モデル実行を停止しました。途中結果は保存されています。",
            force=True,
        )
        raise
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        notifier.close()


def load_status(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir)
    progress = root / "report" / "progress.json"
    if progress.exists():
        return json.loads(progress.read_text(encoding="utf-8"))
    summary = root / "report" / "summary.json"
    if summary.exists():
        return json.loads(summary.read_text(encoding="utf-8"))
    plan = root / "plan.json"
    return {
        "status": "PLANNED" if plan.exists() else "NOT_FOUND",
        "run_dir": str(root),
        "plan": json.loads(plan.read_text(encoding="utf-8")) if plan.exists() else None,
    }


def diagnose_run(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir)
    results_path = root / "results.json"
    if not results_path.exists():
        raise FileNotFoundError(results_path)
    results = json.loads(results_path.read_text(encoding="utf-8"))
    warnings: dict[str, int] = {}
    failures: dict[str, int] = {}
    for row in results:
        diagnostics = row.get("diagnostics") or {}
        for warning in diagnostics.get("warnings", []):
            warnings[warning] = warnings.get(warning, 0) + 1
        for failure in diagnostics.get("failure_codes", []):
            failures[failure] = failures.get(failure, 0) + 1
    return {
        "run_dir": str(root),
        "trials": len(results),
        "warnings": dict(sorted(warnings.items())),
        "failures": dict(sorted(failures.items())),
    }


def compare_run(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir) / "comparison" / "leaderboards.json"
    if not path.exists():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    champions = {protocol: rows[0] if rows else None for protocol, rows in payload.items()}
    return {"run_dir": str(run_dir), "protocol_groups": len(payload), "champions": champions}

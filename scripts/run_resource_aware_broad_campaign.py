#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loto.game.geometry import known_games
from loto.models.catalog_full import ModelEntry, build_catalog
from loto.orchestration.resource_scheduler import (
    ResourcePolicy,
    ResourceScheduler,
    collect_resource_snapshot,
    resolve_resource_plan,
    runtime_resource_class,
)

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class MatrixTask:
    ordinal: int
    model: ModelEntry
    game: str
    resource_class: str

    @property
    def key(self) -> str:
        return f"{self.model.model_id}::{self.game}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute broad catalog model x game runtime/evaluation attempts with live "
            "CPU/RAM/VRAM-aware outer concurrency."
        )
    )
    parser.add_argument("--output", default="runs/resource-aware-broad-campaign")
    parser.add_argument("--models", default="all")
    parser.add_argument("--games", default="all")
    parser.add_argument("--synthetic-rows", type=int, default=160)
    parser.add_argument("--seeds", default="1")
    parser.add_argument("--folds", type=int, default=1)
    parser.add_argument("--test-size", type=int, default=2)
    parser.add_argument("--min-train-size", type=int, default=80)
    parser.add_argument("--holdout-size", type=int, default=4)
    parser.add_argument("--precision", default="32")
    parser.add_argument("--max-trials", type=int, default=1)
    parser.add_argument("--parallel-trials", type=int, default=1)
    parser.add_argument("--outer-worker-cap", type=int, default=8)
    parser.add_argument("--cpus-per-trial", type=int, default=2)
    parser.add_argument("--ram-per-cpu-job-mib", type=int, default=6144)
    parser.add_argument("--gpu-slot-mib", type=int, default=5120)
    parser.add_argument("--gpu-safety-margin-mib", type=int, default=2048)
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--timellm-timeout", type=int, default=5400)
    parser.add_argument("--timellm-max-steps", type=int, default=5)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--loto3", default=None)
    return parser


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head() -> str | None:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def _select_models(expression: str) -> list[ModelEntry]:
    catalog = build_catalog()
    if expression == "all":
        return catalog
    requested = [item.strip() for item in expression.split(",") if item.strip()]
    by_id = {entry.model_id: entry for entry in catalog}
    missing = [model_id for model_id in requested if model_id not in by_id]
    if missing:
        raise SystemExit(f"unknown broad catalog model(s): {', '.join(missing)}")
    return [by_id[model_id] for model_id in requested]


def _select_games(expression: str) -> list[str]:
    canonical = list(known_games())
    if expression == "all":
        return canonical
    requested = [item.strip() for item in expression.split(",") if item.strip()]
    missing = [game for game in requested if game not in canonical]
    if missing:
        raise SystemExit(f"unknown game(s): {', '.join(missing)}")
    return requested


def _build_tasks(models: list[ModelEntry], games: list[str]) -> list[MatrixTask]:
    tasks: list[MatrixTask] = []
    ordinal = 0
    for model in models:
        resource_class = runtime_resource_class(
            model_id=model.model_id,
            library=model.library,
            class_name=model.class_name,
            capabilities=model.capabilities,
        )
        for game in games:
            ordinal += 1
            tasks.append(MatrixTask(ordinal, model, game, resource_class))
    return tasks


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value)


def _campaign_catalog_status(summary: dict[str, Any], model_id: str) -> tuple[str, str]:
    rows = summary.get("results", [])
    if not isinstance(rows, list):
        return "NO_CATALOG_RESULT", "campaign summary results is not a list"
    matches = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("source") == "catalog"
        and row.get("candidate_id") == model_id
    ]
    if len(matches) != 1:
        return "NO_CATALOG_RESULT", f"expected one catalog row, observed {len(matches)}"
    row = matches[0]
    status = str(row.get("status", "UNKNOWN"))
    reason = str(row.get("reason", ""))
    failures = row.get("failures", [])
    if status == "FAILED" and isinstance(failures, list) and failures:
        first = failures[0]
        if isinstance(first, dict):
            failure_type = str(first.get("type", "Failure"))
            failure_reason = str(first.get("reason", ""))
            if failure_reason:
                reason = (
                    f"{reason}; {failure_type}: {failure_reason}"
                    if reason
                    else f"{failure_type}: {failure_reason}"
                )
    return status, reason


def _blocked_gpu_result(task: MatrixTask, case_dir: Path) -> dict[str, Any]:
    result = {
        "ordinal": task.ordinal,
        "task_key": task.key,
        "model_id": task.model.model_id,
        "library": task.model.library,
        "class_name": task.model.class_name,
        "game": task.game,
        "resource_class": task.resource_class,
        "execution_contract": "not-executed",
        "command_rc": None,
        "status": "BLOCKED_GPU_RESOURCE",
        "reason": "no GPU execution slot resolved from the live resource snapshot",
    }
    _atomic_json(case_dir / "FINAL.json", result)
    return result


def _run_task(
    task: MatrixTask,
    *,
    args: argparse.Namespace,
    output_root: Path,
    scheduler: ResourceScheduler,
    loto3: str,
) -> dict[str, Any]:
    case_dir = (
        output_root
        / "cases"
        / (f"{task.ordinal:04d}-{_safe_name(task.model.model_id)}-{_safe_name(task.game)}")
    )
    final_path = case_dir / "FINAL.json"
    if args.resume and final_path.exists():
        return json.loads(final_path.read_text(encoding="utf-8"))
    case_dir.mkdir(parents=True, exist_ok=True)
    attempt = (
        case_dir / f"attempt-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1_000_000_000:09d}"
    )
    attempt.mkdir(parents=True)
    runtime_workdir = attempt / "runtime-workdir"
    runtime_workdir.mkdir()
    _atomic_json(
        attempt / "RUNTIME_CONTEXT.json",
        {
            "repo_root": str(ROOT),
            "runtime_workdir": str(runtime_workdir),
            "task_key": task.key,
        },
    )

    requires_gpu = task.resource_class in {"GPU", "EXCLUSIVE_GPU"}
    lease = scheduler.acquire(
        requires_gpu=requires_gpu,
        lease_id=task.key,
        exclusive_gpu=task.resource_class == "EXCLUSIVE_GPU",
        timeout=max(
            args.timeout, args.timellm_timeout if task.resource_class == "EXCLUSIVE_GPU" else 0
        ),
    )
    started = time.perf_counter()
    result: dict[str, Any] | None = None
    try:
        if task.model.model_id == "nf-timellm":
            execution_contract = "timellm-reduced-gpu-runtime-smoke-v1"
            smoke_output = attempt / "timellm-smoke"
            command = [
                sys.executable,
                str(ROOT / "scripts" / "run_timellm_safe_smoke.py"),
                "--game",
                task.game,
                "--rows",
                str(args.synthetic_rows),
                "--max-steps",
                str(args.timellm_max_steps),
                "--seed",
                args.seeds.split(",")[0],
                "--output",
                str(smoke_output),
            ]
            timeout_seconds = args.timellm_timeout
        else:
            execution_contract = "loto3-unified-development-campaign-v1"
            campaign_output = attempt / "campaign"
            effective_device = "cuda" if requires_gpu else "cpu"
            command = [
                loto3,
                "campaign",
                "--synthetic",
                "--synthetic-rows",
                str(args.synthetic_rows),
                "--games",
                task.game,
                "--models",
                task.model.model_id,
                "--seeds",
                args.seeds,
                "--folds",
                str(args.folds),
                "--test-size",
                str(args.test_size),
                "--min-train-size",
                str(args.min_train_size),
                "--holdout-size",
                str(args.holdout_size),
                "--device",
                effective_device,
                "--precision",
                args.precision,
                "--max-trials",
                str(args.max_trials),
                "--parallel-trials",
                str(args.parallel_trials),
                "--output",
                str(campaign_output),
            ]
            timeout_seconds = args.timeout

        (attempt / "COMMAND.txt").write_text(shlex.join(command) + "\n", encoding="utf-8")
        try:
            proc = subprocess.run(
                command,
                cwd=runtime_workdir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            rc: int | None = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            rc = None
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            timed_out = True

        (attempt / "stdout.log").write_text(stdout or "", encoding="utf-8")
        (attempt / "stderr.log").write_text(stderr or "", encoding="utf-8")

        reason = ""
        if timed_out:
            status = "TIMEOUT"
            reason = f"exceeded {timeout_seconds}s"
        elif task.model.model_id == "nf-timellm":
            result_path = attempt / "timellm-smoke" / "RESULT.json"
            if rc == 0 and result_path.exists():
                smoke = json.loads(result_path.read_text(encoding="utf-8"))
                status = str(smoke.get("status", "UNKNOWN"))
                reason = str(smoke.get("game_compatibility", ""))
            else:
                status = "COMMAND_FAILED"
                reason = f"TimeLLM reduced smoke rc={rc}"
        else:
            summary_path = attempt / "campaign" / "campaign_summary.json"
            combined_log = f"{stdout}\n{stderr}"
            if summary_path.exists():
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                status, reason = _campaign_catalog_status(summary, task.model.model_id)
            elif "Object of type MAE is not JSON serializable" in combined_log:
                status = "POST_RUN_SERIALIZATION_FAILED"
                reason = "NeuralForecast fit/predict evidence reached summary serialization"
            elif rc == 0:
                status = "NO_RESULT_FILE"
                reason = "command completed without campaign_summary.json"
            else:
                status = "COMMAND_FAILED"
                reason = f"campaign rc={rc}"

        result = {
            "ordinal": task.ordinal,
            "task_key": task.key,
            "model_id": task.model.model_id,
            "library": task.model.library,
            "class_name": task.model.class_name,
            "game": task.game,
            "resource_class": task.resource_class,
            "execution_contract": execution_contract,
            "command_rc": rc,
            "status": status,
            "reason": reason,
            "elapsed_seconds": time.perf_counter() - started,
            "lease": lease.to_dict(),
            "attempt_dir": str(attempt),
            "runtime_workdir": str(runtime_workdir),
            "holdout_evaluated": False,
            "prospective_evaluated": False,
            "promotion": False,
        }
    finally:
        scheduler.release(lease)

    if result is None:
        raise RuntimeError(f"task completed without a result payload: {task.key}")
    result["lease"] = lease.to_dict()
    _atomic_json(final_path, result)
    return result


def _write_sha256s(output_root: Path) -> None:
    rows = []
    for path in sorted(output_root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            rows.append(f"{_sha256(path)}  {path.relative_to(output_root)}")
    (output_root / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.outer_worker_cap < 1:
        raise SystemExit("--outer-worker-cap must be >= 1")
    models = _select_models(args.models)
    games = _select_games(args.games)
    tasks = _build_tasks(models, games)

    output_root = Path(args.output)
    if output_root.exists() and not args.resume:
        raise FileExistsError(f"refusing to reuse output root: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    snapshot = collect_resource_snapshot()
    plan = resolve_resource_plan(
        snapshot,
        outer_worker_cap=args.outer_worker_cap,
        cpus_per_trial=args.cpus_per_trial,
        ram_per_cpu_job_mib=args.ram_per_cpu_job_mib,
        gpu_slot_mib=args.gpu_slot_mib,
        safety_margin_mib=args.gpu_safety_margin_mib,
    )
    _atomic_json(output_root / "RESOURCE_SNAPSHOT.json", snapshot.to_dict())
    _atomic_json(output_root / "RESOURCE_PLAN.json", plan.to_dict())
    _atomic_json(
        output_root / "MATRIX_PLAN.json",
        {
            "source_head": _git_head(),
            "catalog_models": len(models),
            "games": games,
            "model_game_pairs": len(tasks),
            "note": "model-game pairs are execution units; catalog identity count is not the pair count",
            "tasks": [
                {
                    "ordinal": task.ordinal,
                    "model_id": task.model.model_id,
                    "library": task.model.library,
                    "class_name": task.model.class_name,
                    "game": task.game,
                    "resource_class": task.resource_class,
                }
                for task in tasks
            ],
        },
    )
    if args.plan_only:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "catalog_models": len(models),
                    "games": len(games),
                    "model_game_pairs": len(tasks),
                    "resource_plan": plan.to_dict(),
                },
                indent=2,
            )
        )
        return 0

    loto3 = args.loto3 or shutil.which("loto3")
    if not loto3:
        raise SystemExit("loto3 executable not found; pass --loto3 /path/to/loto3")

    policy = ResourcePolicy(
        max_parallel_cpu_models=plan.parallel_cpu_models,
        max_parallel_gpu_models=plan.parallel_gpu_models,
        cpus_per_trial=plan.cpus_per_trial,
        gpus_per_trial=1 if plan.parallel_gpu_models else 0,
        max_vram_mib=plan.gpu_slot_mib,
        gpu_memory_safety_margin_mib=plan.safety_margin_mib,
        timeout_seconds=max(args.timeout, args.timellm_timeout),
    )
    scheduler = ResourceScheduler(policy)

    results: list[dict[str, Any]] = []
    cpu_tasks = [task for task in tasks if task.resource_class == "CPU"]
    gpu_tasks = [task for task in tasks if task.resource_class != "CPU"]

    if plan.parallel_gpu_models == 0:
        for task in gpu_tasks:
            case_dir = (
                output_root
                / "cases"
                / (f"{task.ordinal:04d}-{_safe_name(task.model.model_id)}-{_safe_name(task.game)}")
            )
            case_dir.mkdir(parents=True, exist_ok=True)
            results.append(_blocked_gpu_result(task, case_dir))
        gpu_tasks = []

    futures: dict[Future[dict[str, Any]], MatrixTask] = {}
    with ThreadPoolExecutor(max_workers=plan.parallel_cpu_models) as cpu_executor:
        gpu_executor = (
            ThreadPoolExecutor(max_workers=max(1, plan.parallel_gpu_models)) if gpu_tasks else None
        )
        try:
            for task in cpu_tasks:
                future = cpu_executor.submit(
                    _run_task,
                    task,
                    args=args,
                    output_root=output_root,
                    scheduler=scheduler,
                    loto3=loto3,
                )
                futures[future] = task
            if gpu_executor is not None:
                for task in gpu_tasks:
                    future = gpu_executor.submit(
                        _run_task,
                        task,
                        args=args,
                        output_root=output_root,
                        scheduler=scheduler,
                        loto3=loto3,
                    )
                    futures[future] = task

            for future in as_completed(futures):
                task = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "ordinal": task.ordinal,
                        "task_key": task.key,
                        "model_id": task.model.model_id,
                        "library": task.model.library,
                        "class_name": task.model.class_name,
                        "game": task.game,
                        "resource_class": task.resource_class,
                        "execution_contract": "scheduler",
                        "command_rc": None,
                        "status": "SCHEDULER_ERROR",
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
                results.append(result)
                print(
                    f"[{len(results)}/{len(tasks)}] {task.key} -> {result['status']}",
                    flush=True,
                )
        finally:
            if gpu_executor is not None:
                gpu_executor.shutdown(wait=True)

    results.sort(key=lambda row: int(row["ordinal"]))
    counts = Counter(str(row["status"]) for row in results)
    with (output_root / "RESULTS.jsonl").open("w", encoding="utf-8") as stream:
        for row in results:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    _atomic_json(
        output_root / "SUMMARY.json",
        {
            "source_head": _git_head(),
            "catalog_models": len(models),
            "games": len(games),
            "expected_model_game_pairs": len(tasks),
            "observed_model_game_pairs": len(results),
            "matrix_complete": len(results) == len(tasks),
            "status_counts": dict(sorted(counts.items())),
            "resource_plan": plan.to_dict(),
            "holdout_evaluated": False,
            "prospective_evaluated": False,
            "promotion": False,
        },
    )
    _atomic_json(output_root / "RESOURCE_LEASES.json", scheduler.report())
    _write_sha256s(output_root)
    print((output_root / "SUMMARY.json").read_text(encoding="utf-8"))
    return 0 if len(results) == len(tasks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import signal
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

ROOT = Path(__file__).resolve().parents[3]
TASK_FINGERPRINT_VERSION = "resource-aware-broad-task-v2"

__all__ = [
    "MatrixTask",
    "ResourcePolicy",
    "ResourceScheduler",
    "_archive_stale_final",
    "_atomic_json",
    "_build_tasks",
    "_campaign_catalog_status",
    "_canonical_payload_sha256",
    "_execution_contract",
    "_git_head",
    "_outer_executor_workers",
    "_run_process",
    "_run_task",
    "_safe_name",
    "_select_games",
    "_select_models",
    "_task_fingerprint_payload",
    "_terminate_process_tree",
    "build_parser",
    "main",
]


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


def _canonical_payload_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def _execution_contract(task: MatrixTask) -> str:
    if task.model.model_id == "nf-timellm":
        return "timellm-reduced-gpu-runtime-smoke-v1"
    return "loto3-unified-development-campaign-v1"


def _task_fingerprint_payload(
    task: MatrixTask,
    *,
    args: argparse.Namespace,
    loto3: str,
    source_head: str | None,
) -> dict[str, Any]:
    return {
        "version": TASK_FINGERPRINT_VERSION,
        "source_head": source_head,
        "execution_contract": _execution_contract(task),
        "model_id": task.model.model_id,
        "library": task.model.library,
        "class_name": task.model.class_name,
        "game": task.game,
        "resource_class": task.resource_class,
        "loto3": str(loto3),
        "synthetic_rows": args.synthetic_rows,
        "seeds": args.seeds,
        "folds": args.folds,
        "test_size": args.test_size,
        "min_train_size": args.min_train_size,
        "holdout_size": args.holdout_size,
        "precision": args.precision,
        "max_trials": args.max_trials,
        "parallel_trials": args.parallel_trials,
        "timeout": args.timeout,
        "timellm_timeout": args.timellm_timeout,
        "timellm_max_steps": args.timellm_max_steps,
    }


def _archive_stale_final(final_path: Path) -> Path:
    stale = final_path.with_name(
        f"FINAL.stale-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1_000_000_000:09d}.json"
    )
    os.replace(final_path, stale)
    return stale


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


def _terminate_process_tree(
    proc: subprocess.Popen[str], *, grace_seconds: float = 5.0
) -> dict[str, Any]:
    """Terminate the process group/tree before the caller releases its lease."""
    evidence: dict[str, Any] = {
        "root_pid": proc.pid,
        "method": None,
        "term_sent": False,
        "kill_sent": False,
        "tree_cleanup_complete": False,
    }
    if proc.poll() is not None:
        evidence.update(method="already-exited", tree_cleanup_complete=True)
        return evidence

    if os.name == "posix":
        evidence["method"] = "posix-process-group"
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            evidence["term_sent"] = True
        except ProcessLookupError:
            evidence["tree_cleanup_complete"] = True
            return evidence
        try:
            proc.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
                evidence["kill_sent"] = True
            except ProcessLookupError:
                pass
            proc.wait(timeout=grace_seconds)
        evidence["tree_cleanup_complete"] = proc.poll() is not None
        return evidence

    evidence["method"] = "windows-taskkill-tree"
    taskkill = subprocess.run(
        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
        capture_output=True,
        text=True,
        timeout=max(5.0, grace_seconds),
        check=False,
    )
    evidence["term_sent"] = True
    evidence["taskkill_rc"] = taskkill.returncode
    evidence["taskkill_stdout"] = taskkill.stdout
    evidence["taskkill_stderr"] = taskkill.stderr
    try:
        proc.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        evidence["kill_sent"] = True
        proc.wait(timeout=grace_seconds)
    evidence["tree_cleanup_complete"] = proc.poll() is not None
    return evidence


def _run_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
) -> tuple[int | None, str, str, bool, dict[str, Any]]:
    popen_kwargs: dict[str, Any] = {}
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    else:
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **popen_kwargs,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
        return (
            proc.returncode,
            stdout or "",
            stderr or "",
            False,
            {
                "root_pid": proc.pid,
                "method": "normal-exit",
                "term_sent": False,
                "kill_sent": False,
                "tree_cleanup_complete": True,
            },
        )
    except subprocess.TimeoutExpired as exc:
        partial_stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        partial_stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        termination = _terminate_process_tree(proc)
        tail_stdout, tail_stderr = proc.communicate()
        return (
            None,
            partial_stdout + (tail_stdout or ""),
            partial_stderr + (tail_stderr or ""),
            True,
            termination,
        )


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
    source_head = _git_head()
    fingerprint_payload = _task_fingerprint_payload(
        task, args=args, loto3=loto3, source_head=source_head
    )
    fingerprint_sha256 = _canonical_payload_sha256(fingerprint_payload)
    resume_rejected: dict[str, Any] | None = None
    if args.resume and final_path.exists():
        cached = json.loads(final_path.read_text(encoding="utf-8"))
        cached_sha256 = cached.get("task_fingerprint_sha256")
        if source_head is not None and cached_sha256 == fingerprint_sha256:
            return cached
        stale_path = _archive_stale_final(final_path)
        resume_rejected = {
            "reason": "source/config/task fingerprint mismatch or missing source identity",
            "cached_fingerprint_sha256": cached_sha256,
            "current_fingerprint_sha256": fingerprint_sha256,
            "stale_final": str(stale_path),
        }

    case_dir.mkdir(parents=True, exist_ok=True)
    attempt = case_dir / (
        f"attempt-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1_000_000_000:09d}"
    )
    attempt.mkdir(parents=True)
    runtime_workdir = attempt / "runtime-workdir"
    runtime_workdir.mkdir()

    requires_gpu = task.resource_class in {"GPU", "EXCLUSIVE_GPU"}
    lease = scheduler.acquire(
        requires_gpu=requires_gpu,
        lease_id=task.key,
        exclusive_gpu=task.resource_class == "EXCLUSIVE_GPU",
        timeout=max(
            args.timeout,
            args.timellm_timeout if task.resource_class == "EXCLUSIVE_GPU" else 0,
        ),
    )
    started = time.perf_counter()
    result: dict[str, Any] | None = None
    try:
        child_env = os.environ.copy()
        if requires_gpu:
            if lease.gpu_device_index is None:
                raise RuntimeError(f"GPU lease has no physical device assignment: {task.key}")
            child_env["CUDA_VISIBLE_DEVICES"] = str(lease.gpu_device_index)

        _atomic_json(
            attempt / "RUNTIME_CONTEXT.json",
            {
                "repo_root": str(ROOT),
                "runtime_workdir": str(runtime_workdir),
                "task_key": task.key,
                "source_head": source_head,
                "task_fingerprint_sha256": fingerprint_sha256,
                "gpu_device_index": lease.gpu_device_index,
                "cuda_visible_devices": child_env.get("CUDA_VISIBLE_DEVICES"),
            },
        )

        execution_contract = _execution_contract(task)
        if task.model.model_id == "nf-timellm":
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
        rc, stdout, stderr, timed_out, termination = _run_process(
            command,
            cwd=runtime_workdir,
            env=child_env,
            timeout_seconds=timeout_seconds,
        )
        (attempt / "stdout.log").write_text(stdout or "", encoding="utf-8")
        (attempt / "stderr.log").write_text(stderr or "", encoding="utf-8")
        _atomic_json(attempt / "PROCESS_TERMINATION.json", termination)

        reason = ""
        if timed_out:
            status = "TIMEOUT"
            reason = (
                f"exceeded {timeout_seconds}s; process tree cleanup completed before lease release"
            )
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
            "task_fingerprint": fingerprint_payload,
            "task_fingerprint_sha256": fingerprint_sha256,
            "resume_rejected": resume_rejected,
            "command_rc": rc,
            "status": status,
            "reason": reason,
            "elapsed_seconds": time.perf_counter() - started,
            "lease": lease.to_dict(),
            "process_termination": termination,
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


def _outer_executor_workers(*, outer_worker_cap: int, runnable_tasks: int) -> int:
    if outer_worker_cap < 1:
        raise ValueError("outer_worker_cap must be >= 1")
    return min(outer_worker_cap, max(1, runnable_tasks))


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
            "note": (
                "model-game pairs are execution units; "
                "catalog identity count is not the pair count"
            ),
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
        gpu_device_slots=plan.gpu_device_slots,
    )
    scheduler = ResourceScheduler(policy)

    results: list[dict[str, Any]] = []
    runnable_tasks = list(tasks)
    if plan.parallel_gpu_models == 0:
        runnable_tasks = []
        for task in tasks:
            if task.resource_class == "CPU":
                runnable_tasks.append(task)
                continue
            case_dir = (
                output_root
                / "cases"
                / (f"{task.ordinal:04d}-{_safe_name(task.model.model_id)}-{_safe_name(task.game)}")
            )
            case_dir.mkdir(parents=True, exist_ok=True)
            results.append(_blocked_gpu_result(task, case_dir))

    futures: dict[Future[dict[str, Any]], MatrixTask] = {}
    worker_count = _outer_executor_workers(
        outer_worker_cap=args.outer_worker_cap,
        runnable_tasks=len(runnable_tasks),
    )
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        for task in runnable_tasks:
            future = executor.submit(
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
            "outer_executor_workers": worker_count,
            "outer_worker_cap_enforced": worker_count <= args.outer_worker_cap,
            "holdout_evaluated": False,
            "prospective_evaluated": False,
            "promotion": False,
        },
    )
    _atomic_json(output_root / "RESOURCE_LEASES.json", scheduler.report())
    _write_sha256s(output_root)
    print((output_root / "SUMMARY.json").read_text(encoding="utf-8"))
    return 0 if len(results) == len(tasks) else 1

"""Parallel-by-game Unified Campaign runner with read-only live progress."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.evaluation.metric_registry import REQUIRED_POINT_METRICS
from loto.evaluation.path_codec import encode_path_component
from loto.evaluation.protocol_v2 import canonical_json_bytes
from loto.evaluation.unified_campaign import (
    UnifiedCampaignConfig,
    build_campaign_plan,
    run_unified_campaign,
)
from loto.game.geometry import geometry_for, known_games

REPO_ROOT = Path(__file__).resolve().parents[3]
PROGRESS_SCHEMA_VERSION = "1.0.0"


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(canonical_json_bytes(payload) + b"\n")
    os.replace(temp, path)


def _available_cpus() -> tuple[int, ...]:
    if hasattr(os, "sched_getaffinity"):
        cpus = tuple(sorted(os.sched_getaffinity(0)))
        if cpus:
            return cpus
    return tuple(range(max(int(os.cpu_count() or 1), 1)))


def cpu_sets(worker_count: int, reserve_cpus: int) -> list[tuple[int, ...]]:
    """Split available logical CPUs into disjoint worker affinity sets."""

    if worker_count < 1:
        raise ValueError("worker_count must be >= 1")
    if reserve_cpus < 0:
        raise ValueError("reserve_cpus must be >= 0")
    available = _available_cpus()
    reserve = min(reserve_cpus, max(len(available) - 1, 0))
    usable = available[: len(available) - reserve] if reserve else available
    workers = min(worker_count, len(usable))
    per_worker = max(len(usable) // workers, 1)
    output: list[tuple[int, ...]] = []
    start = 0
    for index in range(workers):
        end = len(usable) if index == workers - 1 else start + per_worker
        output.append(tuple(usable[start:end]))
        start = end
    return output


def _limit_worker(cpus: tuple[int, ...]) -> None:
    if not cpus:
        return
    threads = str(len(cpus))
    for key in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "LOKY_MAX_CPU_COUNT",
    ):
        os.environ[key] = threads
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, set(cpus))


def _worker(
    game: str,
    frame: pd.DataFrame,
    config_payload: dict[str, Any],
    output_dir: str,
    cpus: tuple[int, ...],
) -> dict[str, Any]:
    _limit_worker(cpus)
    config = UnifiedCampaignConfig(**config_payload).model_copy(
        update={
            "games": (game,),
            "output_dir": Path(output_dir),
            "cpu_count": max(len(cpus), 1),
        }
    )
    return run_unified_campaign({game: frame}, config)


def _macro_summary(results: list[dict[str, Any]], games: tuple[str, ...]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in results:
        if row["source"] == "catalog":
            grouped.setdefault(row["candidate_id"], []).append(row)
    output: list[dict[str, Any]] = []
    for candidate_id, rows in grouped.items():
        succeeded = [row for row in rows if row["status"] == "SUCCEEDED"]
        complete = len(succeeded) == len(games)
        output.append(
            {
                "candidate_id": candidate_id,
                "games_requested": len(games),
                "games_succeeded": len(succeeded),
                "all_games_complete": complete,
                "macro_hit_at_1": (
                    float(np.mean([row["seed_summary"]["hit_at_1"]["mean"] for row in succeeded]))
                    if complete
                    else None
                ),
                "macro_mae": (
                    float(np.mean([row["seed_summary"]["mae"]["mean"] for row in succeeded]))
                    if complete
                    else None
                ),
                "statuses": {row["game"]: row["status"] for row in rows},
            }
        )
    output.sort(
        key=lambda row: (
            not row["all_games_complete"],
            -(row["macro_hit_at_1"] or -1.0),
            row["candidate_id"],
        )
    )
    return output


def _flat_results(results: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for result in results:
        flat = {
            "game": result["game"],
            "candidate_id": result["candidate_id"],
            "source": result["source"],
            "library": result["library"],
            "task": result["task"],
            "status": result["status"],
            "reason": result.get("reason", ""),
            "protocol_hash": result["protocol_hash"],
        }
        for metric_id in REQUIRED_POINT_METRICS:
            item = result.get("seed_summary", {}).get(metric_id)
            flat[f"{metric_id}_mean"] = item["mean"] if item else None
            flat[f"{metric_id}_variance"] = item["population_variance"] if item else None
            flat[f"{metric_id}_worst"] = item["worst_value"] if item else None
            flat[f"{metric_id}_worst_seed"] = item["worst_seed"] if item else None
        rows.append(flat)
    return pd.DataFrame(rows)


def _checksums(output: Path) -> None:
    paths = sorted(
        path
        for path in output.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(output).as_posix()}"
        for path in paths
    ]
    (output / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_parallel_unified_campaign(
    frames: dict[str, pd.DataFrame],
    config: UnifiedCampaignConfig,
    *,
    workers: int,
    reserve_cpus: int = 2,
) -> dict[str, Any]:
    """Execute independent games concurrently without changing per-game evaluation logic."""

    if workers == 1 or len(config.games) == 1:
        return run_unified_campaign(frames, config)
    output = config.output_dir
    if output.exists():
        raise FileExistsError(f"refusing to reuse campaign output directory: {output}")
    output.mkdir(parents=True)

    plan = build_campaign_plan(config)
    expected_pairs = len(plan)
    (output / "campaign-plan.json").write_bytes(
        canonical_json_bytes(
            {
                "status": "PLANNED",
                "games": list(config.games),
                "model_game_pairs": expected_pairs,
                "plan": plan,
            }
        )
        + b"\n"
    )

    affinities = cpu_sets(min(workers, len(config.games)), reserve_cpus)
    worker_count = len(affinities)
    progress_path = output / "progress.json"
    progress: dict[str, Any] = {
        "schema_version": PROGRESS_SCHEMA_VERSION,
        "status": "RUNNING",
        "execution_mode": "parallel_by_game",
        "workers": worker_count,
        "reserve_cpus": reserve_cpus,
        "games_total": len(config.games),
        "games_completed": 0,
        "model_game_pairs": expected_pairs,
        "games": {
            game: {"status": "PENDING", "output": str(output / "games" / game)}
            for game in config.games
        },
    }
    _atomic_json(progress_path, progress)

    payload = config.model_dump(mode="python")
    summaries: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = {}
        for index, game in enumerate(config.games):
            if game not in frames:
                raise KeyError(f"missing input frame for game={game}")
            cpus = affinities[index % worker_count]
            child_output = output / "games" / game
            progress["games"][game] = {
                "status": "RUNNING",
                "output": str(child_output),
                "cpus": list(cpus),
            }
            future = executor.submit(
                _worker,
                game,
                frames[game],
                payload,
                str(child_output),
                cpus,
            )
            futures[future] = game
        _atomic_json(progress_path, progress)

        for future in as_completed(futures):
            game = futures[future]
            try:
                summaries[game] = future.result()
                progress["games"][game]["status"] = summaries[game]["status"]
            except Exception as exc:  # noqa: BLE001 - persist terminal worker failure
                errors[game] = f"{type(exc).__name__}: {exc}"
                progress["games"][game]["status"] = "FAILED"
                progress["games"][game]["error"] = errors[game]
            progress["games_completed"] = len(summaries) + len(errors)
            _atomic_json(progress_path, progress)

    if errors:
        progress["status"] = "FAILED"
        progress["errors"] = errors
        _atomic_json(progress_path, progress)
        raise RuntimeError(f"parallel campaign worker failures: {errors}")

    ordered = [summaries[game] for game in config.games]
    results = [row for summary in ordered for row in summary["results"]]
    catalog_results = [row for row in results if row["source"] == "catalog"]
    pair_keys = {(row["game"], row["candidate_id"]) for row in catalog_results}
    status_counts: dict[str, int] = {}
    for row in catalog_results:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    leaderboards: dict[str, list[dict[str, Any]]] = {}
    for child in ordered:
        leaderboards.update(child["leaderboards"])
    macro = _macro_summary(results, config.games)

    summary = {
        "schema_version": ordered[0]["schema_version"],
        "status": "SUCCEEDED" if status_counts.get("SUCCEEDED", 0) == expected_pairs else "PARTIAL",
        "created_at_utc": ordered[-1]["created_at_utc"],
        "git_commit": config.git_commit,
        "code_hash": ordered[0]["code_hash"],
        "games": list(config.games),
        "catalog_models": ordered[0]["catalog_models"],
        "expected_model_game_pairs": expected_pairs,
        "observed_model_game_pairs": len(catalog_results),
        "matrix_complete": (
            len(catalog_results) == expected_pairs and len(pair_keys) == expected_pairs
        ),
        "status_counts": status_counts,
        "primary_metric": ordered[0]["primary_metric"],
        "required_metrics": ordered[0]["required_metrics"],
        "required_baselines": ordered[0]["required_baselines"],
        "seeds": list(config.seeds),
        "holdout_evaluated": False,
        "prospective_evaluated": False,
        "promotion": False,
        "execution_mode": "parallel_by_game",
        "workers": worker_count,
        "reserve_cpus": reserve_cpus,
        "results": results,
        "leaderboards": leaderboards,
        "macro_summary": macro,
    }
    (output / "campaign_summary.json").write_bytes(canonical_json_bytes(summary) + b"\n")
    _flat_results(results).to_csv(output / "model_game_results.csv", index=False)
    pd.DataFrame(macro).to_csv(output / "all_game_macro_summary.csv", index=False)
    progress.update(
        {
            "status": summary["status"],
            "games_completed": len(config.games),
            "model_game_pairs_completed": len(catalog_results),
            "matrix_complete": summary["matrix_complete"],
            "status_counts": status_counts,
        }
    )
    _atomic_json(progress_path, progress)
    _checksums(output)
    return summary


def _synthetic(game: str, rows: int, seed: int) -> pd.DataFrame:
    geometry = geometry_for(game)
    rng = np.random.default_rng(seed)
    universe = np.arange(geometry.value_min, geometry.value_max + 1)
    payload = []
    for draw in range(rows):
        if geometry.family == "select":
            values = np.sort(rng.choice(universe, size=geometry.positions, replace=False))
        else:
            values = rng.choice(universe, size=geometry.positions, replace=True)
        payload.append(
            {
                "draw_no": draw + 1,
                **dict(zip(geometry.column_names(), values.tolist(), strict=True)),
            }
        )
    return pd.DataFrame(payload)


def _load_frames(args: argparse.Namespace, games: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    if args.synthetic:
        return {game: _synthetic(game, args.synthetic_rows, args.synthetic_seed) for game in games}
    if not args.input_dir:
        raise ValueError("either --input-dir or --synthetic is required")
    root = Path(args.input_dir)
    return {game: pd.read_csv(root / f"{game}.csv") for game in games}


def _run_args(args: argparse.Namespace) -> int:
    games = tuple(item.strip() for item in args.games.split(",") if item.strip())
    models = (
        tuple(item.strip() for item in args.models.split(",") if item.strip())
        if args.models
        else None
    )
    seeds = tuple(sorted(int(item) for item in args.seeds.split(",") if item.strip()))
    config = UnifiedCampaignConfig(
        output_dir=args.output,
        git_commit=args.git_commit or _git_commit(),
        games=games,
        model_ids=models,
        seeds=seeds,
        folds=args.folds,
        test_size=args.test_size,
        min_train_size=args.min_train_size,
        holdout_size=args.holdout_size,
        gap=args.gap,
        device=args.device,
        precision=args.precision,
        max_trials=args.max_trials,
        parallel_trials=args.parallel_trials,
        max_steps=args.max_steps,
        wall_time_seconds=args.wall_time_seconds,
        gpu_count=args.gpu_count,
        gpu_memory_bytes=args.gpu_memory_bytes,
    )
    if args.plan_only:
        plan = build_campaign_plan(config)
        print(json.dumps({"status": "PLANNED", "plan": plan}, indent=2, ensure_ascii=False))
        return 0
    result = run_parallel_unified_campaign(
        _load_frames(args, games),
        config,
        workers=args.workers,
        reserve_cpus=args.reserve_cpus,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "matrix_complete": result["matrix_complete"],
                "expected_model_game_pairs": result["expected_model_game_pairs"],
                "observed_model_game_pairs": result["observed_model_game_pairs"],
                "status_counts": result["status_counts"],
                "output": str(config.output_dir),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if result["matrix_complete"] else 2


def _gpu_line() -> str:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "GPU: unavailable"
    value = result.stdout.strip()
    return f"GPU: {value}" if value else "GPU: unavailable"


def _status_snapshot(root: Path, hardware: bool) -> tuple[str, bool, str]:
    progress = json.loads((root / "progress.json").read_text(encoding="utf-8"))
    plan = json.loads((root / "campaign-plan.json").read_text(encoding="utf-8"))["plan"]
    by_game: dict[str, list[str]] = {}
    for row in plan:
        by_game.setdefault(row["game"], []).append(row["candidate_id"])
    total = len(plan)
    completed = 0
    lines = ["Unified campaign parallel progress", f"ROOT: {root}"]
    for game, model_ids in by_game.items():
        summary_path = root / "games" / game / "campaign_summary.json"
        if summary_path.is_file():
            done = len(model_ids)
            state = json.loads(summary_path.read_text(encoding="utf-8"))["status"]
        else:
            lock_root = root / "games" / game / "prediction_locks" / game
            indexes = [
                index
                for index, model_id in enumerate(model_ids)
                if (lock_root / encode_path_component(model_id)).is_dir()
            ]
            done = max(indexes) + 1 if indexes else 0
            state = progress["games"].get(game, {}).get("status", "PENDING")
        completed += done
        width = 18
        filled = int(width * done / len(model_ids)) if model_ids else width
        lines.append(
            f"{game:8s} [{'█' * filled}{'·' * (width - filled)}] "
            f"{done:>2}/{len(model_ids):<2} {state}"
        )
    width = 48
    filled = int(width * completed / total) if total else width
    percent = completed / total * 100 if total else 100.0
    lines.insert(
        2,
        f"OVERALL [{'█' * filled}{'·' * (width - filled)}] "
        f"{completed}/{total} ({percent:.2f}%)",
    )
    status = str(progress.get("status", "UNKNOWN"))
    lines.append(f"STATUS: {status}")
    if hardware:
        lines.append(_gpu_line())
    return "\n".join(lines), status in {"SUCCEEDED", "PARTIAL", "FAILED"}, status


def _status_args(args: argparse.Namespace) -> int:
    while True:
        text, finished, status = _status_snapshot(args.root, args.hardware)
        if args.watch:
            print("\033[2J\033[H", end="")
        print(text, flush=True)
        if not args.watch or finished:
            return 1 if status == "FAILED" else 0
        time.sleep(args.interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m loto.evaluation.parallel_campaign")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run independent games in parallel worker processes")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--input-dir")
    run.add_argument("--synthetic", action="store_true")
    run.add_argument("--synthetic-rows", type=int, default=220)
    run.add_argument("--synthetic-seed", type=int, default=7)
    run.add_argument("--games", default=",".join(known_games()))
    run.add_argument("--models")
    run.add_argument("--seeds", default="42,1729,20260730")
    run.add_argument("--folds", type=int, default=5)
    run.add_argument("--test-size", type=int, default=20)
    run.add_argument("--min-train-size", type=int, default=100)
    run.add_argument("--holdout-size", type=int, default=50)
    run.add_argument("--gap", type=int, default=0)
    run.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    run.add_argument("--precision", choices=["32", "16-mixed", "bf16-mixed"], default="32")
    run.add_argument("--max-trials", type=int, default=10)
    run.add_argument("--parallel-trials", type=int, default=1)
    run.add_argument("--max-steps", type=int, default=50)
    run.add_argument("--wall-time-seconds", type=int, default=1800)
    run.add_argument("--gpu-count", type=int, default=0)
    run.add_argument("--gpu-memory-bytes", type=int, default=0)
    run.add_argument("--workers", type=int, default=6)
    run.add_argument("--reserve-cpus", type=int, default=2)
    run.add_argument("--git-commit")
    run.add_argument("--plan-only", action="store_true")
    run.set_defaults(func=_run_args)

    status = sub.add_parser("status", help="read parallel progress without mutating the run")
    status.add_argument("--root", type=Path, required=True)
    status.add_argument("--watch", action="store_true")
    status.add_argument("--interval", type=float, default=2.0)
    status.add_argument("--hardware", action="store_true")
    status.set_defaults(func=_status_args)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        if args.workers < 1:
            raise SystemExit("--workers must be >= 1")
        if args.reserve_cpus < 0:
            raise SystemExit("--reserve-cpus must be >= 0")
    elif args.interval <= 0:
        raise SystemExit("--interval must be > 0")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

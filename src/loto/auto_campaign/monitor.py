from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

STAGE_DIRECTORIES = (
    "p0-inventory",
    "plan",
    "p1-smoke",
    "p2-api-coverage",
    "p2-model-config-coverage",
    "p3-hpo",
    "p3-validation-replay",
    "p3-accuracy-promotion",
    "p4-oof",
    "p4-accuracy-policy",
    "p5-holdout",
    "p5-accuracy-ensemble",
    "p6-prospective",
    "p6-accuracy-prospective",
)


def bar(current: int, total: int, width: int = 40) -> str:
    ratio = 0.0 if total <= 0 else min(1.0, max(0.0, current / total))
    complete = int(width * ratio)
    return "[" + "#" * complete + "-" * (width - complete) + "]"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _clear() -> None:
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")


def render(run: Path) -> None:
    progress = _read_json(run / "progress.json")
    manifest = _read_json(run / "manifest.json")
    completed = int(progress.get("completed", manifest.get("completed_tasks", 0)) or 0)
    failed = int(progress.get("failed", manifest.get("failed_tasks", 0)) or 0)
    total = int(progress.get("total", manifest.get("planned_tasks", 0)) or 0)
    percent = 0.0 if total == 0 else 100.0 * (completed + failed) / total
    _clear()
    print("=" * 88)
    print(" NeuralForecast all-AutoModel campaign")
    print("=" * 88)
    print(f"RUN      : {run}")
    print(f"STAGE    : {progress.get('stage', manifest.get('stage', 'NOT_READY'))}")
    print(f"STATUS   : {manifest.get('status', 'RUNNING' if progress else 'NOT_READY')}")
    print(
        f"PROGRESS : {bar(completed + failed, total)} {completed + failed}/{total} {percent:6.2f}%"
    )
    print(f"PASS     : {completed}")
    print(f"FAIL     : {failed}")
    print(f"CURRENT  : {progress.get('current')}")
    print()
    print("Ctrl+C stops only the monitor.")


def render_group(group: Path) -> None:
    _clear()
    print("=" * 104)
    print(" NeuralForecast all-AutoModel full campaign")
    print("=" * 104)
    print(f"GROUP: {group}")
    print()
    total_done = 0
    total_tasks = 0
    for name in STAGE_DIRECTORIES:
        stage = group / name
        progress = _read_json(stage / "progress.json")
        manifest = _read_json(stage / "manifest.json")
        completed = int(progress.get("completed", manifest.get("completed_tasks", 0)) or 0)
        failed = int(progress.get("failed", manifest.get("failed_tasks", 0)) or 0)
        total = int(progress.get("total", manifest.get("planned_tasks", 0)) or 0)
        if manifest:
            status = str(manifest.get("status", "UNKNOWN"))
            if total == 0:
                completed, total = 1, 1
        elif progress:
            status = "RUNNING"
        elif stage.exists():
            status = "STARTING"
        else:
            status = "WAIT"
        done = completed + failed
        total_done += done
        total_tasks += total
        percent = 0.0 if total == 0 else 100.0 * done / total
        print(
            f"{name:27s} {bar(done, total, width=28)} "
            f"{done:7d}/{total:<7d} {percent:6.2f}% "
            f"PASS={completed:<7d} FAIL={failed:<5d} {status}"
        )
    print()
    overall = 0.0 if total_tasks == 0 else 100.0 * total_done / total_tasks
    print(
        f"Known-task progress {bar(total_done, total_tasks, width=48)} "
        f"{total_done}/{total_tasks} {overall:6.2f}%"
    )
    group_manifest = _read_json(group / "CAMPAIGN_MANIFEST.json")
    if group_manifest:
        print(f"FINAL STATUS: {group_manifest.get('status')}")
    print()
    print("Ctrl+C stops only the monitor.")


def main() -> None:
    parser = argparse.ArgumentParser()
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--run", type=Path)
    selection.add_argument("--group", type=Path)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        while True:
            if args.group is not None:
                render_group(args.group.resolve())
            else:
                render(args.run.resolve())
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nMONITOR_STOPPED")


if __name__ == "__main__":
    main()

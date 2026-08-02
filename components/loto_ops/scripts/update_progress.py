#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def bar(percent: float, width: int = 28) -> str:
    percent = max(0.0, min(100.0, percent))
    filled = int(round(width * percent / 100.0))
    return "█" * filled + "░" * (width - filled)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--state", required=True)
    p.add_argument("--title", default="scheduled pipeline")
    p.add_argument("--reason", default="schedule")
    p.add_argument("--step", type=int, required=True)
    p.add_argument("--total", type=int, required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--status", choices=["pending", "running", "success", "failed", "warning", "skipped"], required=True)
    p.add_argument("--message", default="")
    p.add_argument("--log-file", default="")
    args = p.parse_args()

    path = Path(args.state)
    path.parent.mkdir(parents=True, exist_ok=True)
    old = {}
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            old = {}

    started_at = old.get("started_at") or now()
    steps = old.get("steps") or []
    if len(steps) != args.total:
        steps = [
            {"index": i + 1, "name": "", "status": "pending", "started_at": None, "finished_at": None}
            for i in range(args.total)
        ]

    idx = max(1, min(args.step, args.total)) - 1
    steps[idx]["name"] = args.name
    steps[idx]["status"] = args.status
    if args.status == "running" and not steps[idx].get("started_at"):
        steps[idx]["started_at"] = now()
    if args.status in {"success", "failed", "warning", "skipped"}:
        steps[idx]["finished_at"] = now()
    steps[idx]["message"] = args.message

    done = sum(1 for s in steps if s.get("status") in {"success", "skipped"})
    percent = 100.0 * done / max(1, args.total)
    if args.status == "running":
        percent = 100.0 * (idx + 0.15) / max(1, args.total)
    elif args.status == "skipped":
        percent = 100.0 * (idx + 1) / max(1, args.total)
    elif args.status in {"failed", "warning"}:
        percent = 100.0 * idx / max(1, args.total)

    payload = {
        "title": args.title,
        "reason": args.reason,
        "status": args.status,
        "message": args.message,
        "current_step": args.name,
        "current_index": idx + 1,
        "total_steps": args.total,
        "percent": round(percent, 2),
        "bar": bar(percent),
        "started_at": started_at,
        "updated_at": now(),
        "log_file": args.log_file,
        "steps": steps,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    print(f"[progress] {payload['bar']} {payload['percent']:6.2f}% | {args.status}: {args.name} {args.message}".rstrip(), flush=True)


if __name__ == "__main__":
    main()

from __future__ import annotations

import json

from loto_ops.config import load_settings


def latest_runs(limit: int = 20) -> list[dict]:
    settings = load_settings()
    runs_dir = settings.paths.runs_dir
    if not runs_dir.exists():
        return []
    out = []
    for p in sorted(
        runs_dir.glob("*/run_manifest.json"), key=lambda x: x.stat().st_mtime, reverse=True
    )[:limit]:
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out

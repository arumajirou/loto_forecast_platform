from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from loto_ops.config import AppSettings


@dataclass
class BenchmarkResult:
    name: str
    seconds: float
    status: str
    detail: dict[str, object] = field(default_factory=dict)
    error: str = ""


class BenchmarkRunner:
    """Small harness for comparing safe pipeline stages.

    It does not run destructive DB operations unless the caller explicitly wraps those
    operations. The default use is to time local artifact generation or COPY loading.
    """

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.out_dir = settings.paths.reports_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def time_callable(
        self, name: str, func: Callable[[], dict[str, object] | None]
    ) -> BenchmarkResult:
        start = time.perf_counter()
        try:
            detail = func() or {}
            return BenchmarkResult(
                name=name,
                seconds=round(time.perf_counter() - start, 3),
                status="success",
                detail=detail,
            )
        except Exception as exc:
            return BenchmarkResult(
                name=name,
                seconds=round(time.perf_counter() - start, 3),
                status="failed",
                error=str(exc),
            )

    def write_results(self, results: list[BenchmarkResult]) -> Path:
        path = self.out_dir / "benchmark_results.json"
        path.write_text(
            json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def write_system_probe_script(self) -> Path:
        path = self.out_dir / "system_probe_commands.sh"
        path.write_text(
            """#!/usr/bin/env bash
set -euo pipefail

echo '=== CPU ==='
mpstat -P ALL 1 3 || true

echo '=== IO ==='
iostat -xz 1 3 || true

echo '=== process cpu/io/mem ==='
pidstat -u -d -r -p ALL 1 3 || true

echo '=== postgres activity ==='
PGPASSWORD="${DB_PASSWORD:-CHANGE_ME}" psql -h "${DB_HOST:-127.0.0.1}" -p "${DB_PORT:-5432}" -U "${DB_USER:-loto}" -d "${DB_NAME:-loto}" -X -P pager=off -c "
SELECT pid, state, wait_event_type, wait_event, now() - query_start AS elapsed, left(query, 160) AS query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
" || true
""",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

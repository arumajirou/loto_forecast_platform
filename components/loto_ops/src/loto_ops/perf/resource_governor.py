from __future__ import annotations

import json
import os
import platform
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text

from loto_ops.config import AppSettings
from loto_ops.db.connection import make_engine


@dataclass(frozen=True)
class PerfPlan:
    mode: str
    cpu_count: int
    physical_cpu_guess: int
    memory_total_gb: float
    memory_available_gb: float
    polars_threads: int
    copy_jobs: int
    exog_workers: int
    unified_engine: str
    unified_write_mode: str
    full_exog_allowed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def env(self) -> dict[str, str]:
        return {
            "POLARS_MAX_THREADS": str(self.polars_threads),
            "RAYON_NUM_THREADS": str(self.polars_threads),
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_MAX_THREADS": str(max(1, min(self.polars_threads, 16))),
            "LOTO_OPS_MODE": self.mode,
        }


class ResourceGovernor:
    """Choose stage-specific resource limits rather than blindly using all cores.

    The pipeline has CPU-heavy, DB-heavy, and I/O-heavy stages.  Using all cores for
    every stage can make PostgreSQL and the disk wait queue slower.  This class
    creates conservative but high-throughput defaults and exposes diagnostics for
    CLI/Web UI.
    """

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def memory_info(self) -> tuple[float, float]:
        total_kb = 0
        available_kb = 0
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    available_kb = int(line.split()[1])
        total_gb = total_kb / 1024 / 1024 if total_kb else 0.0
        available_gb = available_kb / 1024 / 1024 if available_kb else 0.0
        return round(total_gb, 2), round(available_gb, 2)

    def physical_cpu_guess(self) -> int:
        cpu_count = os.cpu_count() or 1
        # Python stdlib has no portable physical-core count.  Hyperthreading is common,
        # so half the logical count is a reasonable safe estimate for DB/COPY jobs.
        return max(1, cpu_count // 2)

    def db_max_connections(self) -> int | None:
        try:
            engine = make_engine(self.settings.db)
            try:
                with engine.begin() as conn:
                    value = conn.execute(text("SHOW max_connections")).scalar()
                    return int(value) if value is not None else None
            finally:
                engine.dispose()
        except Exception:
            return None

    def exog_table_summary(self) -> list[dict[str, Any]]:
        sql = text(
            """
            SELECT schemaname, relname, n_live_tup::bigint,
                   pg_total_relation_size(format('%I.%I', schemaname, relname))::bigint
            FROM pg_stat_user_tables
            WHERE schemaname IN ('exog', 'exog_full', 'exog_disabled', 'dataset')
            ORDER BY pg_total_relation_size(format('%I.%I', schemaname, relname)) DESC
            """
        )
        try:
            engine = make_engine(self.settings.db)
            try:
                with engine.begin() as conn:
                    rows = conn.execute(sql).all()
            finally:
                engine.dispose()
        except Exception:
            return []
        return [
            {
                "schema": r[0],
                "table": r[1],
                "estimated_rows": int(r[2] or 0),
                "size_bytes": int(r[3] or 0),
                "size_mb": round(int(r[3] or 0) / 1024 / 1024, 2),
            }
            for r in rows
        ]

    def make_plan(self, mode: str = "auto") -> PerfPlan:
        cpu_count = os.cpu_count() or 1
        physical = self.physical_cpu_guess()
        total_gb, available_gb = self.memory_info()
        db_max = self.db_max_connections() or 100

        requested = mode
        full_allowed = available_gb >= 48 and cpu_count >= 16
        if mode == "auto":
            # Daily operation should be stable and comparable.  Full 1000-column joins
            # are only selected automatically on very large machines.
            if full_allowed and os.getenv("LOTO_OPS_AUTO_FULL", "0") == "1":
                mode = "full"
                reason = (
                    "auto selected full because LOTO_OPS_AUTO_FULL=1 and resources are sufficient"
                )
            else:
                mode = "light"
                reason = "auto selected light to avoid 1000-column PostgreSQL write bottleneck"
        else:
            reason = f"explicit mode={mode}"

        polars_threads = max(1, min(cpu_count - 2 if cpu_count > 4 else cpu_count, 32))
        copy_jobs = max(1, min(physical, 8, max(1, db_max // 8)))
        exog_workers = max(1, min(physical, 16))
        if mode == "full":
            # Leave more memory bandwidth and PostgreSQL headroom for wide joins.
            copy_jobs = max(1, min(copy_jobs, 4))
            exog_workers = max(1, min(exog_workers, 8))

        return PerfPlan(
            mode=mode,
            cpu_count=cpu_count,
            physical_cpu_guess=physical,
            memory_total_gb=total_gb,
            memory_available_gb=available_gb,
            polars_threads=polars_threads,
            copy_jobs=copy_jobs,
            exog_workers=exog_workers,
            unified_engine="postgres-ctas",
            unified_write_mode="copy/ctas",
            full_exog_allowed=full_allowed,
            reason=f"requested={requested}; {reason}",
        )

    def diagnostics(self, mode: str = "auto") -> dict[str, Any]:
        plan = self.make_plan(mode=mode)
        return {
            "environment": {
                "platform": platform.platform(),
                "kernel": platform.release(),
                "python": platform.python_version(),
                "wsl": (
                    "microsoft" in platform.release().lower() or bool(os.getenv("WSL_DISTRO_NAME"))
                ),
                "desktop": os.getenv("XDG_CURRENT_DESKTOP", ""),
                "uv": shutil.which("uv"),
                "psql": shutil.which("psql"),
            },
            "plan": plan.to_dict(),
            "plan_env": plan.env(),
            "db": {"max_connections": self.db_max_connections()},
            "tables": self.exog_table_summary(),
        }

    def print_shell_exports(self, mode: str = "auto") -> None:
        for key, value in self.make_plan(mode=mode).env().items():
            print(f"export {key}={json.dumps(value)}")

from __future__ import annotations

import fcntl
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from loto_ops.config import AppSettings

_AUDIT_FIELDS = [
    "rows_checked",
    "series_count",
    "duplicate_keys",
    "source_last_date",
    "target_last_date",
    "latest_rows",
    "latest_series",
    "lag1_mismatches",
    "lag2_mismatches",
    "lag3_mismatches",
    "lag7_mismatches",
    "lag14_mismatches",
    "lag28_mismatches",
    "roll_mean3_mismatches",
    "roll_mean7_mismatches",
    "roll_mean14_mismatches",
    "roll_mean28_mismatches",
    "expanding_mean_mismatches",
    "calendar_year_mismatches",
    "calendar_month_mismatches",
    "calendar_day_mismatches",
    "calendar_dow_mismatches",
    "calendar_week_mismatches",
    "calendar_doy_mismatches",
    "calendar_weekend_mismatches",
    "calendar_month_start_mismatches",
    "calendar_month_end_mismatches",
    "roll_std7_mismatches",
    "roll_std14_mismatches",
    "roll_std28_mismatches",
    "roll_min7_mismatches",
    "roll_max7_mismatches",
    "roll_min14_mismatches",
    "roll_max14_mismatches",
    "expanding_std_mismatches",
    "days_since_first_mismatches",
    "row_no_mismatches",
    "leak_diff1_uses_current_y",
    "leak_diff7_uses_current_y",
    "leak_stat_mean_full_sample",
]

_SAFE_ZERO_FIELDS = [
    "duplicate_keys",
    "lag1_mismatches",
    "lag2_mismatches",
    "lag3_mismatches",
    "lag7_mismatches",
    "lag14_mismatches",
    "lag28_mismatches",
    "roll_mean3_mismatches",
    "roll_mean7_mismatches",
    "roll_mean14_mismatches",
    "roll_mean28_mismatches",
    "expanding_mean_mismatches",
    "calendar_year_mismatches",
    "calendar_month_mismatches",
    "calendar_day_mismatches",
    "calendar_dow_mismatches",
    "calendar_week_mismatches",
    "calendar_doy_mismatches",
    "calendar_weekend_mismatches",
    "calendar_month_start_mismatches",
    "calendar_month_end_mismatches",
    "roll_std7_mismatches",
    "roll_std14_mismatches",
    "roll_std28_mismatches",
    "roll_min7_mismatches",
    "roll_max7_mismatches",
    "roll_min14_mismatches",
    "roll_max14_mismatches",
    "expanding_std_mismatches",
    "days_since_first_mismatches",
    "row_no_mismatches",
]

_SAFE_COLUMNS = [
    "feature_contract",
    "loto",
    "unique_id",
    "ts_type",
    "ds",
    "target_y",
    "feat_year",
    "feat_month",
    "feat_day",
    "feat_dayofweek",
    "feat_weekofyear",
    "feat_dayofyear",
    "feat_is_weekend",
    "feat_is_month_start",
    "feat_is_month_end",
    "feat_days_since_first",
    "feat_row_no_in_group",
    "hist_lag_1",
    "hist_lag_2",
    "hist_lag_3",
    "hist_lag_7",
    "hist_lag_14",
    "hist_lag_28",
    "hist_roll_mean_3",
    "hist_roll_mean_7",
    "hist_roll_mean_14",
    "hist_roll_mean_28",
    "hist_roll_std_7",
    "hist_roll_std_14",
    "hist_roll_std_28",
    "hist_roll_min_7",
    "hist_roll_max_7",
    "hist_roll_min_14",
    "hist_roll_max_14",
    "hist_expanding_mean",
    "hist_expanding_std",
]

_EXCLUDED_FEATURES = [
    "hist_diff_*: current target y is used",
    "stat_y_*: full-sample statistics leak future rows",
    "loto_y_ts_exog_y/current y: target, not an exogenous input",
    "feat_proc_seconds/feat_exec_lag_sec: runtime metadata",
    "hist_ewm_mean_*: excluded until the exact recursive formula is frozen and audited",
]

_ROLLING_CONTRACT = {
    "source_shift": 1,
    "mean_min_periods": {
        "hist_roll_mean_3": 3,
        "hist_roll_mean_7": 7,
        "hist_roll_mean_14": 14,
        "hist_roll_mean_28": 28,
    },
    "std_min_periods": {
        "hist_roll_std_7": 7,
        "hist_roll_std_14": 14,
        "hist_roll_std_28": 28,
    },
    "std_ddof": 1,
    "row_number_base": 1,
}


class ExogRunner:
    """Build, audit, and publish Loto exogenous features.

    loto_forecast replaces ``exog.loto_y_ts_exog`` by dropping and recreating
    it. A persistent view over that table would therefore block refreshes.
    The leakage-safe dataset is maintained as an independently refreshed
    physical table.
    """

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.project = settings.paths.loto_forecast_project
        self.ops_root = Path(__file__).resolve().parents[3]
        self.exog_pipeline = self.project / "src" / "resources" / "exog_pipeline.py"
        self.audit_sql = self.ops_root / "scripts" / "sql" / "loto7_safe_feature_audit_v3.sql"
        self.refresh_sql = self.ops_root / "scripts" / "sql" / "refresh_loto7_safe_table_v3.sql"
        self.report_path = self.ops_root / "artifacts" / "reports" / "loto7_exog_audit_latest.json"

    def needs_sqlalchemy_inspect_patch(self) -> bool:
        if not self.exog_pipeline.exists():
            return False
        text = self.exog_pipeline.read_text(encoding="utf-8")
        return "sqlalchemy_inspect" in text and "inspect as sqlalchemy_inspect" not in text

    def patch_sqlalchemy_inspect(self) -> bool:
        if not self.needs_sqlalchemy_inspect_patch():
            return False
        text = self.exog_pipeline.read_text(encoding="utf-8")
        lines = text.splitlines()
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("from sqlalchemy") or line.startswith("import sqlalchemy"):
                insert_at = i + 1
        lines.insert(insert_at, "from sqlalchemy import inspect as sqlalchemy_inspect")
        self.exog_pipeline.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True

    def _base_env(self) -> dict[str, str]:
        db = self.settings.db
        env = os.environ.copy()
        for name in (
            "VIRTUAL_ENV",
            "PYTHONHOME",
            "UV_PROJECT_ENVIRONMENT",
        ):
            env.pop(name, None)
        env.update(
            {
                "PYTHONPATH": str(self.project / "src"),
                "DB_HOST": db.host,
                "DB_PORT": str(db.port),
                "DB_USER": db.user,
                "DB_PASSWORD": db.password,
                "DB_NAME": db.database,
                "PGPASSWORD": db.password,
            }
        )
        return env

    def _python_bin(self, env: dict[str, str]) -> str:
        configured = env.get("LOTO_FORECAST_PYTHON")

        candidates = [
            configured,
            str(
                Path(
                    env.get(
                        "LOTO_PLATFORM_ROOT",
                        "/mnt/e/env/ts/loto_forecast_platform",
                    )
                )
                / ".venv"
                / "bin"
                / "python"
            ),
            str(self.project.parent.parent / ".venv" / "bin" / "python"),
        ]

        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return candidate

        raise FileNotFoundError(
            "loto_forecast Python was not found: "
            + ", ".join(candidate for candidate in candidates if candidate)
        )

    def _psql_command(self) -> list[str]:
        db = self.settings.db
        return [
            "psql",
            "-X",
            "--quiet",
            "--set=ON_ERROR_STOP=1",
            "-h",
            db.host,
            "-p",
            str(db.port),
            "-U",
            db.user,
            "-d",
            db.database,
        ]

    def _psql_sql(
        self,
        sql: str,
        env: dict[str, str],
        *,
        capture: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*self._psql_command(), "-c", sql],
            env=env,
            text=True,
            capture_output=capture,
            check=True,
        )

    def _psql_file(
        self,
        path: Path,
        env: dict[str, str],
        *,
        tuples_only: bool = False,
        field_separator: str = "\t",
        capture: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        if not path.is_file():
            raise FileNotFoundError(f"SQL file was not found: {path}")
        command = [*self._psql_command()]
        if tuples_only:
            command.extend(["-A", "-t", "-F", field_separator])
        command.extend(["-f", str(path)])
        return subprocess.run(
            command,
            env=env,
            text=True,
            capture_output=capture,
            check=True,
        )

    def _drop_legacy_dependent_views(self, env: dict[str, str]) -> None:
        self._psql_sql(
            """
            DROP VIEW IF EXISTS exog.loto7_exog_safe_v1;
            """,
            env,
        )

    def _audit(self, env: dict[str, str]) -> dict[str, Any]:
        result = self._psql_file(
            self.audit_sql,
            env,
            tuples_only=True,
            capture=True,
        )
        rows = [line for line in result.stdout.splitlines() if line.strip()]
        if len(rows) != 1:
            raise RuntimeError(
                f"Expected exactly one audit row, received {len(rows)}. stdout={result.stdout!r}"
            )

        values = rows[0].split("\t")
        if len(values) != len(_AUDIT_FIELDS):
            raise RuntimeError(
                f"Unexpected audit column count: expected={len(_AUDIT_FIELDS)} actual={len(values)}"
            )

        audit: dict[str, Any] = {}
        date_fields = {"source_last_date", "target_last_date"}
        for key, value in zip(_AUDIT_FIELDS, values, strict=True):
            audit[key] = value if key in date_fields else int(value)

        audit["contract_version"] = "loto7-safe-v3"
        audit["rolling_contract"] = _ROLLING_CONTRACT
        audit["safe_columns"] = _SAFE_COLUMNS
        audit["excluded_features"] = _EXCLUDED_FEATURES

        failures: dict[str, Any] = {}
        if audit["rows_checked"] <= 0:
            failures["rows_checked"] = audit["rows_checked"]
        if audit["series_count"] != 7:
            failures["series_count"] = audit["series_count"]
        if audit["latest_rows"] != 7:
            failures["latest_rows"] = audit["latest_rows"]
        if audit["latest_series"] != 7:
            failures["latest_series"] = audit["latest_series"]
        if audit["source_last_date"] != audit["target_last_date"]:
            failures["freshness"] = {
                "source_last_date": audit["source_last_date"],
                "target_last_date": audit["target_last_date"],
            }
        for key in _SAFE_ZERO_FIELDS:
            if audit[key] != 0:
                failures[key] = audit[key]

        audit["status"] = "PASS" if not failures else "FAIL"
        audit["failures"] = failures

        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(audit, ensure_ascii=False, indent=2))

        if failures:
            raise RuntimeError(f"Loto7 exogenous feature audit failed. See {self.report_path}")
        return audit

    def _refresh_safe_table(self, env: dict[str, str]) -> None:
        self._psql_file(self.refresh_sql, env)

    def run(self, parallel_workers: int = 4) -> None:
        db = self.settings.db
        env = self._base_env()
        python_bin = self._python_bin(env)
        lock_path = Path(env.get("LOTO_EXOG_LOCK_FILE", "/tmp/loto_ops_build_exog.lock"))
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        with lock_path.open("w", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            self.patch_sqlalchemy_inspect()
            self._drop_legacy_dependent_views(env)

            subprocess.run(
                [
                    python_bin,
                    "-m",
                    "loto_forecast.cli",
                    "build-exog",
                    "--host",
                    db.host,
                    "--port",
                    str(db.port),
                    "--user",
                    db.user,
                    "--database",
                    db.database,
                    "--source-schema",
                    "dataset",
                    "--source-table",
                    "loto_y_ts",
                    "--target-schema",
                    "exog",
                    "--target-table",
                    "loto_y_ts_exog",
                    "--if-exists",
                    "replace",
                    "--group-cols",
                    "loto,unique_id,ts_type",
                    "--time-col",
                    "ds",
                    "--target-col",
                    "y",
                    "--parallel-workers",
                    str(parallel_workers),
                    "--no-enable-anomaly-features",
                ],
                cwd=self.project,
                env=env,
                check=True,
            )

            self._audit(env)
            self._refresh_safe_table(env)

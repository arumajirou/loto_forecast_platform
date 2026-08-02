from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from loto_ops.config import AppSettings
from loto_ops.db.connection import make_engine
from loto_ops.perf.resource_governor import ResourceGovernor

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
BASE_KEYS = {"loto", "unique_id", "ts_type", "ds"}
HIST_KEYS = {"loto", "unique_id", "ds"}
ROW_ID_KEYS = {"loto_y_ts_row_id"}


@dataclass(frozen=True)
class ExogCandidate:
    schema: str
    table: str
    columns: list[str]
    join_keys: list[str]
    selected_columns: list[str]
    skipped_reason: str = ""

    @property
    def fqname(self) -> str:
        return f"{self.schema}.{self.table}"


@dataclass
class UnifiedBuildResult:
    mode: str
    output_table: str
    rows: int
    columns: int
    seconds: float
    selected_exog: list[dict[str, Any]] = field(default_factory=list)
    skipped_exog: list[dict[str, Any]] = field(default_factory=list)
    engine: str = "postgres-ctas"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "engine": self.engine,
            "output_table": self.output_table,
            "rows": self.rows,
            "columns": self.columns,
            "seconds": self.seconds,
            "selected_exog": self.selected_exog,
            "skipped_exog": self.skipped_exog,
        }


class UnifiedFastBuilder:
    """Build unified dataset inside PostgreSQL using CTAS instead of pandas.to_sql.

    This avoids the slow path observed in logs where Python CPU drops to 0% while
    pandas/to_sql sends a wide DataFrame to PostgreSQL row-by-row/batch-by-batch.
    Light mode intentionally joins only exog.loto_y_ts_exog for stable daily runs.
    """

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.db = settings.db
        self.engine = make_engine(settings.db)

    def close(self) -> None:
        self.engine.dispose()

    def quote(self, ident: str) -> str:
        if not IDENT_RE.match(ident):
            # Still support arbitrary names safely by double-quote escaping.
            return '"' + ident.replace('"', '""') + '"'
        return f'"{ident}"'

    def fq(self, schema: str, table: str) -> str:
        return f"{self.quote(schema)}.{self.quote(table)}"

    def table_exists(self, conn, schema: str, table: str) -> bool:
        return bool(
            conn.execute(
                text(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM information_schema.tables
                      WHERE table_schema=:schema AND table_name=:table
                    )
                    """
                ),
                {"schema": schema, "table": table},
            ).scalar()
        )

    def columns(self, conn, schema: str, table: str) -> list[str]:
        rows = conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema=:schema AND table_name=:table
                ORDER BY ordinal_position
                """
            ),
            {"schema": schema, "table": table},
        ).all()
        return [str(r[0]) for r in rows]

    def exog_tables(self, conn) -> list[str]:
        rows = conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema='exog'
                  AND table_type='BASE TABLE'
                ORDER BY CASE WHEN table_name='loto_y_ts_exog' THEN 0 ELSE 1 END,
                         table_name
                """
            )
        ).all()
        return [str(r[0]) for r in rows]

    def _join_keys_for_exog(self, base_cols: set[str], exog_cols: set[str]) -> list[str] | None:
        if BASE_KEYS.issubset(base_cols) and BASE_KEYS.issubset(exog_cols):
            return ["loto", "unique_id", "ts_type", "ds"]
        less_specific = {"loto", "ts_type", "ds"}
        if less_specific.issubset(base_cols) and less_specific.issubset(exog_cols):
            return ["loto", "ts_type", "ds"]
        if ROW_ID_KEYS.issubset(base_cols) and ROW_ID_KEYS.issubset(exog_cols):
            return ["loto_y_ts_row_id"]
        return None

    def select_exog_candidates(
        self,
        conn,
        *,
        mode: str,
        max_exog_cols: int | None = None,
        include_tables: list[str] | None = None,
    ) -> tuple[list[ExogCandidate], list[ExogCandidate]]:
        base_cols = set(self.columns(conn, "dataset", "loto_y_ts"))
        if include_tables:
            table_names = include_tables
        elif mode == "light":
            table_names = ["loto_y_ts_exog"]
        else:
            table_names = self.exog_tables(conn)

        selected: list[ExogCandidate] = []
        skipped: list[ExogCandidate] = []
        for table_name in table_names:
            if not self.table_exists(conn, "exog", table_name):
                skipped.append(ExogCandidate("exog", table_name, [], [], [], "missing"))
                continue
            cols = self.columns(conn, "exog", table_name)
            join_keys = self._join_keys_for_exog(base_cols, set(cols))
            if not join_keys:
                skipped.append(
                    ExogCandidate("exog", table_name, cols, [], [], "unsupported join keys")
                )
                continue
            selected_cols = [c for c in cols if c not in set(join_keys)]
            if max_exog_cols is not None:
                selected_cols = selected_cols[: max(0, int(max_exog_cols))]
            if not selected_cols:
                skipped.append(
                    ExogCandidate("exog", table_name, cols, join_keys, [], "no selectable columns")
                )
                continue
            selected.append(ExogCandidate("exog", table_name, cols, join_keys, selected_cols))
        return selected, skipped

    def _build_select_sql(
        self,
        conn,
        *,
        exog: list[ExogCandidate],
        output_schema: str,
        output_table: str,
        unlogged: bool,
    ) -> str:
        base_cols = self.columns(conn, "dataset", "loto_y_ts")
        hist_cols = (
            self.columns(conn, "dataset", "loto_hist_feat")
            if self.table_exists(conn, "dataset", "loto_hist_feat")
            else []
        )
        selected_names: set[str] = set()
        select_items: list[str] = []

        for col in base_cols:
            select_items.append(f"b.{self.quote(col)} AS {self.quote(col)}")
            selected_names.add(col)

        for col in hist_cols:
            if col in HIST_KEYS:
                continue
            out_name = col if col not in selected_names else f"hist_{col}"
            select_items.append(f"h.{self.quote(col)} AS {self.quote(out_name)}")
            selected_names.add(out_name)

        for idx, cand in enumerate(exog):
            alias = f"e{idx}"
            prefix = "" if len(exog) == 1 and cand.table == "loto_y_ts_exog" else f"{cand.table}_"
            for col in cand.selected_columns:
                out_name = col if (not prefix and col not in selected_names) else f"{prefix}{col}"
                if out_name in selected_names:
                    out_name = f"{cand.table}_{col}"
                select_items.append(f"{alias}.{self.quote(col)} AS {self.quote(out_name)}")
                selected_names.add(out_name)

        joins = [
            f"FROM {self.fq('dataset', 'loto_y_ts')} b",
        ]
        if hist_cols:
            joins.append(
                f"LEFT JOIN {self.fq('dataset', 'loto_hist_feat')} h "
                'ON b."loto" = h."loto" '
                'AND b."unique_id" = h."unique_id" '
                'AND b."ds" = h."ds"'
            )
        for idx, cand in enumerate(exog):
            alias = f"e{idx}"
            cond = " AND ".join(
                f"b.{self.quote(k)} = {alias}.{self.quote(k)}" for k in cand.join_keys
            )
            joins.append(f"LEFT JOIN {self.fq(cand.schema, cand.table)} {alias} ON {cond}")

        table_kind = "UNLOGGED TABLE" if unlogged else "TABLE"
        staging = f"{output_table}_staging"
        return (
            f"DROP TABLE IF EXISTS {self.fq(output_schema, staging)} CASCADE;\n"
            f"CREATE {table_kind} {self.fq(output_schema, staging)} AS\n"
            "SELECT\n  " + ",\n  ".join(select_items) + "\n" + "\n".join(joins) + ";\n"
        )

    def build(
        self,
        *,
        mode: str = "light",
        output_schema: str = "dataset",
        output_table: str = "loto_y_ts_unified",
        max_exog_cols: int | None = None,
        include_tables: list[str] | None = None,
        unlogged: bool = True,
    ) -> UnifiedBuildResult:
        started = time.perf_counter()
        plan = ResourceGovernor(self.settings).make_plan(mode=mode)
        effective_mode = plan.mode if mode == "auto" else mode
        selected_payload: list[dict[str, Any]] = []
        skipped_payload: list[dict[str, Any]] = []

        try:
            with self.engine.begin() as conn:
                conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {self.quote(output_schema)}"))
                conn.execute(text("SET synchronous_commit = 'off'"))
                conn.execute(text("SET work_mem = '256MB'"))
                conn.execute(text("SET maintenance_work_mem = '2GB'"))
                selected, skipped = self.select_exog_candidates(
                    conn,
                    mode=effective_mode,
                    max_exog_cols=max_exog_cols,
                    include_tables=include_tables,
                )
                if not selected and effective_mode in {"light", "auto"}:
                    raise RuntimeError(
                        "No supported exog table selected. Expected exog.loto_y_ts_exog."
                    )

                selected_payload = [
                    {
                        "table": cand.fqname,
                        "join_keys": cand.join_keys,
                        "selected_columns": len(cand.selected_columns),
                    }
                    for cand in selected
                ]
                skipped_payload = [
                    {
                        "table": cand.fqname,
                        "reason": cand.skipped_reason,
                        "columns": len(cand.columns),
                    }
                    for cand in skipped
                ]

                create_sql = self._build_select_sql(
                    conn,
                    exog=selected,
                    output_schema=output_schema,
                    output_table=output_table,
                    unlogged=unlogged,
                )
                for stmt in [s.strip() for s in create_sql.split(";\n") if s.strip()]:
                    conn.execute(text(stmt))

                staging = f"{output_table}_staging"
                conn.execute(
                    text(f"DROP TABLE IF EXISTS {self.fq(output_schema, output_table)} CASCADE")
                )
                conn.execute(
                    text(
                        f"ALTER TABLE {self.fq(output_schema, staging)} "
                        f"RENAME TO {self.quote(output_table)}"
                    )
                )
                # Useful read/query indexes.
                # CREATE INDEX after load is faster than maintaining indexes during load.
                cols = set(self.columns(conn, output_schema, output_table))
                if {"loto", "unique_id", "ts_type", "ds"}.issubset(cols):
                    conn.execute(
                        text(
                            f"CREATE INDEX IF NOT EXISTS idx_{output_table}_key "
                            f"ON {self.fq(output_schema, output_table)} "
                            "(loto, unique_id, ts_type, ds)"
                        )
                    )
                elif {"unique_id", "ds"}.issubset(cols):
                    conn.execute(
                        text(
                            f"CREATE INDEX IF NOT EXISTS idx_{output_table}_uid_ds "
                            f"ON {self.fq(output_schema, output_table)} (unique_id, ds)"
                        )
                    )
                conn.execute(text(f"ANALYZE {self.fq(output_schema, output_table)}"))
                rows = int(
                    conn.execute(
                        text(f"SELECT COUNT(*) FROM {self.fq(output_schema, output_table)}")
                    ).scalar()
                    or 0
                )
                col_count = len(self.columns(conn, output_schema, output_table))
        finally:
            self.close()

        return UnifiedBuildResult(
            mode=effective_mode,
            output_table=f"{output_schema}.{output_table}",
            rows=rows,
            columns=col_count,
            seconds=round(time.perf_counter() - started, 3),
            selected_exog=selected_payload,
            skipped_exog=skipped_payload,
        )

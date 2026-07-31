from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loto.registry.database import Database


class PlatformRegistry:
    """Production-oriented append-first platform registry."""

    def __init__(self, url: str | Path):
        if isinstance(url, Path) or "://" not in str(url):
            url = f"sqlite:///{url}"
        self.db = Database(str(url))
        self._init_schema()

    def _init_schema(self) -> None:
        serial = "BIGSERIAL" if self.db.kind == "postgres" else "INTEGER"
        auto = "" if self.db.kind == "postgres" else " AUTOINCREMENT"
        with self.db.connect() as con:
            cur = con.cursor()
            cur.execute(f"""CREATE TABLE IF NOT EXISTS audit_log(
                id {serial} PRIMARY KEY{auto}, created_at TEXT NOT NULL, actor TEXT NOT NULL,
                action TEXT NOT NULL, object_type TEXT NOT NULL, object_id TEXT NOT NULL,
                reason TEXT NOT NULL, payload_json TEXT NOT NULL)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS runs(
                run_id TEXT PRIMARY KEY, status TEXT NOT NULL, current_stage TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, config_hash TEXT,
                release_id TEXT, error_json TEXT)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS tasks(
                run_id TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL,
                attempt INTEGER NOT NULL, started_at TEXT, finished_at TEXT,
                input_hash TEXT, output_uri TEXT, error_json TEXT,
                PRIMARY KEY(run_id, stage, attempt))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS models(
                model_id TEXT PRIMARY KEY, model_type TEXT NOT NULL, status TEXT NOT NULL,
                artifact_uri TEXT NOT NULL, metrics_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL, created_at TEXT NOT NULL)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS forecasts(
                forecast_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, draw_id TEXT NOT NULL,
                status TEXT NOT NULL, sealed_json TEXT NOT NULL, verified INTEGER NOT NULL,
                created_at TEXT NOT NULL, scored_at TEXT, score_json TEXT)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS releases(
                release_id TEXT PRIMARY KEY, status TEXT NOT NULL, bundle_json TEXT NOT NULL,
                signature TEXT, created_at TEXT NOT NULL, promoted_at TEXT)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS approvals(
                object_type TEXT NOT NULL, object_id TEXT NOT NULL, action TEXT NOT NULL,
                requested_by TEXT NOT NULL, approved_by TEXT, status TEXT NOT NULL,
                reason TEXT NOT NULL, created_at TEXT NOT NULL, decided_at TEXT,
                PRIMARY KEY(object_type, object_id, action))""")

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def audit(
        self,
        actor: str,
        action: str,
        object_type: str,
        object_id: str,
        reason: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        p = self.db.placeholder
        with self.db.connect() as con:
            con.cursor().execute(
                f"INSERT INTO audit_log(created_at,actor,action,object_type,object_id,reason,payload_json) VALUES({','.join([p] * 7)})",
                (
                    self._now(),
                    actor,
                    action,
                    object_type,
                    object_id,
                    reason,
                    json.dumps(payload or {}, ensure_ascii=False, default=str),
                ),
            )

    def create_run(self, run_id: str, *, config_hash: str = "") -> None:
        p = self.db.placeholder
        now = self._now()
        with self.db.connect() as con:
            con.cursor().execute(
                f"INSERT INTO runs(run_id,status,current_stage,created_at,updated_at,config_hash) VALUES({','.join([p] * 6)})",
                (run_id, "PENDING", None, now, now, config_hash),
            )

    def update_run(
        self,
        run_id: str,
        *,
        status: str,
        current_stage: str | None = None,
        error: dict | None = None,
        release_id: str | None = None,
    ) -> None:
        p = self.db.placeholder
        with self.db.connect() as con:
            con.cursor().execute(
                f"UPDATE runs SET status={p},current_stage={p},updated_at={p},error_json={p},release_id=COALESCE({p},release_id) WHERE run_id={p}",
                (
                    status,
                    current_stage,
                    self._now(),
                    json.dumps(error) if error else None,
                    release_id,
                    run_id,
                ),
            )

    def record_task(
        self,
        run_id: str,
        stage: str,
        status: str,
        *,
        attempt: int = 1,
        input_hash: str = "",
        output_uri: str | None = None,
        error: dict | None = None,
    ) -> None:
        p = self.db.placeholder
        now = self._now()
        started = now if status in {"RUNNING", "SUCCEEDED", "FAILED"} else None
        finished = now if status in {"SUCCEEDED", "FAILED", "SKIPPED"} else None
        sql = f"""INSERT INTO tasks(run_id,stage,status,attempt,started_at,finished_at,input_hash,output_uri,error_json)
                  VALUES({",".join([p] * 9)})
                  ON CONFLICT(run_id,stage,attempt) DO UPDATE SET status=excluded.status,
                  finished_at=excluded.finished_at,output_uri=excluded.output_uri,error_json=excluded.error_json"""
        with self.db.connect() as con:
            con.cursor().execute(
                sql,
                (
                    run_id,
                    stage,
                    status,
                    attempt,
                    started,
                    finished,
                    input_hash,
                    output_uri,
                    json.dumps(error) if error else None,
                ),
            )

    def completed_stages(self, run_id: str) -> set[str]:
        p = self.db.placeholder
        with self.db.connect() as con:
            rows = (
                con.cursor()
                .execute(
                    f"SELECT DISTINCT stage FROM tasks WHERE run_id={p} AND status='SUCCEEDED'",
                    (run_id,),
                )
                .fetchall()
            )
        return {str(r[0]) for r in rows}

    def register_model(
        self,
        model_id: str,
        model_type: str,
        artifact_uri: str,
        metrics: dict,
        metadata: dict,
        status: str = "CANDIDATE",
    ) -> None:
        p = self.db.placeholder
        with self.db.connect() as con:
            con.cursor().execute(
                f"INSERT INTO models VALUES({','.join([p] * 7)}) ON CONFLICT(model_id) DO NOTHING",
                (
                    model_id,
                    model_type,
                    status,
                    artifact_uri,
                    json.dumps(metrics),
                    json.dumps(metadata),
                    self._now(),
                ),
            )

    def register_forecast(
        self,
        forecast_id: str,
        run_id: str,
        draw_id: str,
        sealed: dict,
        verified: bool,
        status: str = "SEALED",
    ) -> None:
        p = self.db.placeholder
        with self.db.connect() as con:
            con.cursor().execute(
                f"INSERT INTO forecasts(forecast_id,run_id,draw_id,status,sealed_json,verified,created_at) VALUES({','.join([p] * 7)}) ON CONFLICT(forecast_id) DO NOTHING",
                (
                    forecast_id,
                    run_id,
                    draw_id,
                    status,
                    json.dumps(sealed, ensure_ascii=False),
                    int(verified),
                    self._now(),
                ),
            )

    def score_forecast(self, forecast_id: str, score: dict) -> None:
        p = self.db.placeholder
        with self.db.connect() as con:
            con.cursor().execute(
                f"UPDATE forecasts SET status='SCORED',scored_at={p},score_json={p} WHERE forecast_id={p}",
                (self._now(), json.dumps(score), forecast_id),
            )

    def request_approval(
        self, object_type: str, object_id: str, action: str, requested_by: str, reason: str
    ) -> None:
        p = self.db.placeholder
        with self.db.connect() as con:
            con.cursor().execute(
                f"INSERT INTO approvals VALUES({','.join([p] * 9)}) ON CONFLICT(object_type,object_id,action) DO UPDATE SET requested_by=excluded.requested_by,status='PENDING',reason=excluded.reason,created_at=excluded.created_at",
                (
                    object_type,
                    object_id,
                    action,
                    requested_by,
                    None,
                    "PENDING",
                    reason,
                    self._now(),
                    None,
                ),
            )

    def decide_approval(
        self, object_type: str, object_id: str, action: str, approved_by: str, approved: bool
    ) -> None:
        p = self.db.placeholder
        with self.db.connect() as con:
            row = (
                con.cursor()
                .execute(
                    f"SELECT requested_by FROM approvals WHERE object_type={p} AND object_id={p} AND action={p}",
                    (object_type, object_id, action),
                )
                .fetchone()
            )
            if row is None:
                raise KeyError("approval request not found")
            if str(row[0]) == approved_by:
                raise PermissionError("requester and approver must be different")
            con.cursor().execute(
                f"UPDATE approvals SET approved_by={p},status={p},decided_at={p} WHERE object_type={p} AND object_id={p} AND action={p}",
                (
                    approved_by,
                    "APPROVED" if approved else "REJECTED",
                    self._now(),
                    object_type,
                    object_id,
                    action,
                ),
            )

    def list_rows(self, table: str, limit: int = 100) -> list[dict]:
        if table not in {
            "runs",
            "tasks",
            "models",
            "forecasts",
            "releases",
            "approvals",
            "audit_log",
        }:
            raise ValueError("unsupported table")
        with self.db.connect() as con:
            rows = (
                con.cursor()
                .execute(
                    f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT {int(limit)}"
                    if self.db.kind == "sqlite"
                    else f"SELECT * FROM {table} LIMIT {int(limit)}"
                )
                .fetchall()
            )
        return [
            dict(r) if hasattr(r, "keys") else {str(i): v for i, v in enumerate(r)} for r in rows
        ]

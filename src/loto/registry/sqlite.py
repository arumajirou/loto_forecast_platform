from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path


class Registry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _init(self) -> None:
        with self._connect() as con:
            con.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS stage_events(
              id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, stage TEXT NOT NULL,
              status TEXT NOT NULL, created_at TEXT NOT NULL, payload_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS forecasts(
              forecast_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, created_at TEXT NOT NULL,
              sealed_json TEXT NOT NULL, verified INTEGER NOT NULL);
            """)

    def record_stage(self, run_id: str, stage: str, status: str, payload: dict) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO stage_events(run_id,stage,status,created_at,payload_json) VALUES(?,?,?,?,?)",
                (
                    run_id,
                    stage,
                    status,
                    datetime.now(UTC).isoformat(),
                    json.dumps(payload, ensure_ascii=False, default=str),
                ),
            )

    def list_stage_events(self, run_id: str) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM stage_events WHERE run_id=? ORDER BY id", (run_id,)
            ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def record_forecast(self, forecast_id: str, run_id: str, sealed: dict, verified: bool) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO forecasts VALUES(?,?,?,?,?)",
                (
                    forecast_id,
                    run_id,
                    datetime.now(UTC).isoformat(),
                    json.dumps(sealed, ensure_ascii=False),
                    int(verified),
                ),
            )

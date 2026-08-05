from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import MemoryClaim, MemoryEvent

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS memory_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    project TEXT NOT NULL,
    task_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    source TEXT NOT NULL,
    commit_sha TEXT,
    branch TEXT,
    protocol_hash TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_events_scope
ON memory_events(project, task_id, created_at);

CREATE TABLE IF NOT EXISTS memory_claims (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL UNIQUE,
    project TEXT NOT NULL,
    task_id TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    statement TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    supersedes_claim_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(source_event_id) REFERENCES memory_events(event_id)
);
CREATE INDEX IF NOT EXISTS idx_memory_claims_scope
ON memory_claims(project, task_id, verified, created_at);
"""


class SQLiteMemoryStore:
    """Append-only local fallback store.

    Production deployments should point the MCP layer at PostgreSQL. This store
    keeps local development and tests deterministic without requiring services.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(_SCHEMA)

    def append_event(self, event: MemoryEvent) -> None:
        self._connection.execute(
            """
            INSERT INTO memory_events(
                event_id, project, task_id, event_type, payload_json, source,
                commit_sha, branch, protocol_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.project,
                event.task_id,
                event.event_type,
                json.dumps(event.payload, ensure_ascii=False, sort_keys=True),
                event.source,
                event.commit_sha,
                event.branch,
                event.protocol_hash,
                event.created_at.isoformat(),
            ),
        )
        self._connection.commit()

    def append_claim(self, claim: MemoryClaim) -> None:
        self._connection.execute(
            """
            INSERT INTO memory_claims(
                claim_id, project, task_id, claim_type, statement,
                source_event_id, verified, supersedes_claim_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                claim.claim_id,
                claim.project,
                claim.task_id,
                claim.claim_type.value,
                claim.statement,
                claim.source_event_id,
                int(claim.verified),
                claim.supersedes_claim_id,
                claim.created_at.isoformat(),
            ),
        )
        self._connection.commit()

    def search_events(self, project: str, query: str, limit: int = 20) -> list[dict]:
        escaped = f"%{query.replace('%', '')}%"
        rows = self._connection.execute(
            """
            SELECT * FROM memory_events
            WHERE project = ? AND (payload_json LIKE ? OR event_type LIKE ? OR source LIKE ?)
            ORDER BY sequence DESC LIMIT ?
            """,
            (project, escaped, escaped, escaped, limit),
        ).fetchall()
        return [
            {
                **dict(row),
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def task_status(self, project: str, task_id: str) -> dict:
        event = self._connection.execute(
            """
            SELECT * FROM memory_events
            WHERE project = ? AND task_id = ?
            ORDER BY sequence DESC LIMIT 1
            """,
            (project, task_id),
        ).fetchone()
        claims = self._connection.execute(
            """
            SELECT COUNT(*) AS count, SUM(verified) AS verified_count
            FROM memory_claims WHERE project = ? AND task_id = ?
            """,
            (project, task_id),
        ).fetchone()
        return {
            "project": project,
            "task_id": task_id,
            "latest_event": dict(event) if event else None,
            "claim_count": int(claims["count"] or 0),
            "verified_claim_count": int(claims["verified_count"] or 0),
        }

    def close(self) -> None:
        self._connection.close()

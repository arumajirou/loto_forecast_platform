from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import MemoryClaim, MemoryEvent


class PostgresMemoryStore:
    """PostgreSQL-backed append-only memory store.

    Imports are lazy so the core harness can run without PostgreSQL libraries.
    """

    def __init__(self, database_url: str, initialize: bool = True) -> None:
        try:
            import psycopg
            from pgvector.psycopg import register_vector
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "install psycopg[binary] and pgvector through the harness extra"
            ) from exc
        self._psycopg = psycopg
        self.connection = psycopg.connect(database_url, autocommit=False)
        if initialize:
            schema_path = Path(__file__).with_name("postgres_schema.sql")
            with self.connection.cursor() as cursor:
                cursor.execute(schema_path.read_text(encoding="utf-8"))
            self.connection.commit()
        register_vector(self.connection)

    def _project_id(self, project: str) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO projects(name) VALUES (%s)
                ON CONFLICT(name) DO UPDATE SET name = excluded.name
                RETURNING project_id
                """,
                (project,),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("project upsert returned no project_id")
            return int(row[0])

    def _ensure_task(self, project_id: int, event: MemoryEvent) -> None:
        payload = event.payload
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tasks(
                    task_id, project_id, repository, worktree, branch,
                    base_sha, objective, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(task_id) DO UPDATE SET
                    branch = COALESCE(excluded.branch, tasks.branch),
                    base_sha = COALESCE(excluded.base_sha, tasks.base_sha),
                    status = excluded.status,
                    updated_at = now()
                """,
                (
                    event.task_id,
                    project_id,
                    str(payload.get("repository") or "unknown"),
                    str(payload.get("worktree") or "unknown"),
                    event.branch,
                    event.commit_sha,
                    str(payload.get("objective") or event.event_type),
                    str(payload.get("status") or "ACTIVE"),
                ),
            )

    def append_event(self, event: MemoryEvent) -> None:
        project_id = self._project_id(event.project)
        self._ensure_task(project_id, event)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO memory_events(
                    event_id, project_id, task_id, event_type, payload, source,
                    commit_sha, branch, protocol_hash, artifact_sha256, created_at
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
                """,
                (
                    event.event_id,
                    project_id,
                    event.task_id,
                    event.event_type,
                    json.dumps(event.payload, ensure_ascii=False, sort_keys=True),
                    event.source,
                    event.commit_sha,
                    event.branch,
                    event.protocol_hash,
                    event.payload.get("artifact_sha256"),
                    event.created_at,
                ),
            )
        self.connection.commit()

    def append_claim(
        self,
        claim: MemoryClaim,
        *,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
        embedding_revision: str | None = None,
        chunker_version: str | None = None,
    ) -> None:
        project_id = self._project_id(claim.project)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO memory_claims(
                    claim_id, project_id, task_id, claim_type, statement,
                    source_event_id, verified, supersedes_claim_id, embedding,
                    embedding_model, embedding_revision, chunker_version, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    claim.claim_id,
                    project_id,
                    claim.task_id,
                    claim.claim_type.value,
                    claim.statement,
                    claim.source_event_id,
                    claim.verified,
                    claim.supersedes_claim_id,
                    embedding,
                    embedding_model,
                    embedding_revision,
                    chunker_version,
                    claim.created_at,
                ),
            )
        self.connection.commit()

    def search_events(self, project: str, query: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.connection.cursor(row_factory=self._psycopg.rows.dict_row) as cursor:
            cursor.execute(
                """
                SELECT e.event_id::text, p.name AS project, e.task_id,
                       e.event_type, e.payload, e.source, e.commit_sha,
                       e.branch, e.protocol_hash, e.created_at
                FROM memory_events e
                JOIN projects p ON p.project_id = e.project_id
                WHERE p.name = %s
                  AND (
                    e.payload::text ILIKE %s OR e.event_type ILIKE %s
                    OR e.source ILIKE %s
                  )
                ORDER BY e.sequence DESC LIMIT %s
                """,
                (project, f"%{query}%", f"%{query}%", f"%{query}%", limit),
            )
            return list(cursor.fetchall())

    def search_claims(
        self,
        project: str,
        query: str,
        *,
        embedding: list[float] | None = None,
        verified_only: bool = True,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        verified_clause = "AND c.verified = TRUE" if verified_only else ""
        if embedding is None:
            sql = f"""
                SELECT c.claim_id::text, c.task_id, c.claim_type, c.statement,
                       c.verified, c.source_event_id::text, c.created_at,
                       ts_rank(to_tsvector('simple', c.statement),
                               plainto_tsquery('simple', %s)) AS text_score
                FROM memory_claims c
                JOIN projects p ON p.project_id = c.project_id
                WHERE p.name = %s {verified_clause}
                  AND to_tsvector('simple', c.statement)
                      @@ plainto_tsquery('simple', %s)
                ORDER BY text_score DESC, c.sequence DESC LIMIT %s
            """
            params: tuple[Any, ...] = (query, project, query, limit)
        else:
            sql = f"""
                SELECT c.claim_id::text, c.task_id, c.claim_type, c.statement,
                       c.verified, c.source_event_id::text, c.created_at,
                       ts_rank(to_tsvector('simple', c.statement),
                               plainto_tsquery('simple', %s)) AS text_score,
                       CASE WHEN c.embedding IS NULL THEN 0
                            ELSE 1 - (c.embedding <=> %s) END AS semantic_score
                FROM memory_claims c
                JOIN projects p ON p.project_id = c.project_id
                WHERE p.name = %s {verified_clause}
                ORDER BY (0.55 * CASE WHEN c.embedding IS NULL THEN 0
                                     ELSE 1 - (c.embedding <=> %s) END
                         + 0.45 * ts_rank(to_tsvector('simple', c.statement),
                                         plainto_tsquery('simple', %s))) DESC,
                         c.sequence DESC
                LIMIT %s
            """
            params = (query, embedding, project, embedding, query, limit)
        with self.connection.cursor(row_factory=self._psycopg.rows.dict_row) as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())

    def task_status(self, project: str, task_id: str) -> dict[str, Any]:
        with self.connection.cursor(row_factory=self._psycopg.rows.dict_row) as cursor:
            cursor.execute(
                """
                SELECT t.*, p.name AS project
                FROM tasks t JOIN projects p ON p.project_id = t.project_id
                WHERE p.name = %s AND t.task_id = %s
                """,
                (project, task_id),
            )
            task = cursor.fetchone()
            cursor.execute(
                """
                SELECT COUNT(*) AS claim_count,
                       COUNT(*) FILTER (WHERE c.verified) AS verified_claim_count
                FROM memory_claims c
                JOIN projects p ON p.project_id = c.project_id
                WHERE p.name = %s AND c.task_id = %s
                """,
                (project, task_id),
            )
            counts = cursor.fetchone()
        if counts is None:
            claim_count = 0
            verified_claim_count = 0
        else:
            claim_count = int(counts.get("claim_count") or 0)
            verified_claim_count = int(counts.get("verified_claim_count") or 0)
        return {
            "task": task,
            "claim_count": claim_count,
            "verified_claim_count": verified_claim_count,
        }

    def close(self) -> None:
        self.connection.close()

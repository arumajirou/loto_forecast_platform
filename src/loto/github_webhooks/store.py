from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from loto.github_webhooks.contracts import (
    GitHubWebhookEnvelope,
    HandlerClaim,
    HandlerStatus,
    StoreOutcome,
)


ERROR_CODE_RE = re.compile(r"^[A-Z0-9_]{1,64}$")


class WebhookStore:
    def __init__(
        self,
        path: str | Path,
        *,
        max_attempts: int,
        base_backoff_seconds: int,
        max_backoff_seconds: int,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_attempts = max_attempts
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self._init_schema()

    @staticmethod
    def _iso(value: datetime) -> str:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(UTC).isoformat()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS github_webhook_schema (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS github_webhook_deliveries (
                    repository_id INTEGER NOT NULL,
                    delivery_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    action TEXT,
                    payload_sha256 TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT,
                    last_error_code TEXT,
                    trace_id TEXT NOT NULL,
                    key_id TEXT NOT NULL,
                    normalized_json TEXT NOT NULL,
                    PRIMARY KEY (repository_id, delivery_id)
                );
                CREATE TABLE IF NOT EXISTS github_webhook_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repository_id INTEGER NOT NULL,
                    delivery_id TEXT NOT NULL,
                    handler TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    available_at TEXT NOT NULL,
                    locked_at TEXT,
                    locked_by TEXT,
                    last_error_code TEXT,
                    UNIQUE(repository_id, delivery_id, handler),
                    FOREIGN KEY(repository_id, delivery_id)
                        REFERENCES github_webhook_deliveries(repository_id, delivery_id)
                );
                CREATE TABLE IF NOT EXISTS github_webhook_status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repository_id INTEGER NOT NULL,
                    delivery_id TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    FOREIGN KEY(repository_id, delivery_id)
                        REFERENCES github_webhook_deliveries(repository_id, delivery_id)
                );
                CREATE TABLE IF NOT EXISTS github_webhook_dead_letters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repository_id INTEGER NOT NULL,
                    delivery_id TEXT NOT NULL,
                    handler TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    error_code TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(repository_id, delivery_id, handler),
                    FOREIGN KEY(repository_id, delivery_id)
                        REFERENCES github_webhook_deliveries(repository_id, delivery_id)
                );
                CREATE INDEX IF NOT EXISTS idx_github_webhook_outbox_ready
                    ON github_webhook_outbox(status, available_at);
                """
            )
            row = connection.execute(
                "SELECT version FROM github_webhook_schema WHERE version=1"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO github_webhook_schema(version, applied_at) VALUES(1, ?)",
                    (self._iso(datetime.now(UTC)),),
                )

    @staticmethod
    def _canonical_json(envelope: GitHubWebhookEnvelope) -> str:
        return json.dumps(
            envelope.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def store_delivery(
        self,
        envelope: GitHubWebhookEnvelope,
        handlers: tuple[str, ...],
    ) -> StoreOutcome:
        delivery_id = str(envelope.delivery_id)
        received_at = self._iso(envelope.received_at)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT payload_sha256
                FROM github_webhook_deliveries
                WHERE repository_id=? AND delivery_id=?
                """,
                (envelope.repository_id, delivery_id),
            ).fetchone()
            if existing is not None:
                connection.commit()
                if existing["payload_sha256"] == envelope.payload_sha256:
                    return StoreOutcome.DUPLICATE
                return StoreOutcome.CONFLICT

            connection.execute(
                """
                INSERT INTO github_webhook_deliveries(
                    repository_id, delivery_id, event_type, action, payload_sha256,
                    received_at, status, attempt, trace_id, key_id, normalized_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    envelope.repository_id,
                    delivery_id,
                    envelope.event_type.value,
                    envelope.action,
                    envelope.payload_sha256,
                    received_at,
                    "QUEUED",
                    0,
                    envelope.trace_id,
                    envelope.key_id,
                    self._canonical_json(envelope),
                ),
            )
            connection.execute(
                """
                INSERT INTO github_webhook_status_history(
                    repository_id, delivery_id, from_status, to_status, reason_code, changed_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    envelope.repository_id,
                    delivery_id,
                    None,
                    "QUEUED",
                    "DELIVERY_ACCEPTED",
                    received_at,
                ),
            )
            for handler in handlers:
                connection.execute(
                    """
                    INSERT INTO github_webhook_outbox(
                        repository_id, delivery_id, handler, status, attempt, available_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        envelope.repository_id,
                        delivery_id,
                        handler,
                        HandlerStatus.PENDING.value,
                        0,
                        received_at,
                    ),
                )
            connection.commit()
        return StoreOutcome.ACCEPTED

    def claim_ready(
        self,
        *,
        worker_id: str,
        now: datetime,
        limit: int = 10,
    ) -> list[HandlerClaim]:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", worker_id):
            raise ValueError("invalid worker_id")
        if limit < 1 or limit > 100:
            raise ValueError("limit must be 1..100")
        now_text = self._iso(now)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT o.id, o.repository_id, o.delivery_id, o.handler, o.attempt,
                       d.payload_sha256, d.normalized_json, d.trace_id
                FROM github_webhook_outbox o
                JOIN github_webhook_deliveries d
                  ON d.repository_id=o.repository_id AND d.delivery_id=o.delivery_id
                WHERE o.status IN ('PENDING','RETRY') AND o.available_at <= ?
                ORDER BY o.id
                LIMIT ?
                """,
                (now_text, limit),
            ).fetchall()
            claims: list[HandlerClaim] = []
            for row in rows:
                attempt = int(row["attempt"]) + 1
                connection.execute(
                    """
                    UPDATE github_webhook_outbox
                    SET status='PROCESSING', attempt=?, locked_at=?, locked_by=?
                    WHERE id=? AND status IN ('PENDING','RETRY')
                    """,
                    (attempt, now_text, worker_id, row["id"]),
                )
                claims.append(
                    HandlerClaim(
                        claim_id=row["id"],
                        repository_id=row["repository_id"],
                        delivery_id=row["delivery_id"],
                        handler=row["handler"],
                        attempt=attempt,
                        payload_sha256=row["payload_sha256"],
                        normalized_json=row["normalized_json"],
                        trace_id=row["trace_id"],
                        locked_by=worker_id,
                        locked_at=now,
                    )
                )
            connection.commit()
        return claims

    def _retry_delay_seconds(self, delivery_id: str, handler: str, attempt: int) -> float:
        base = min(
            self.max_backoff_seconds,
            self.base_backoff_seconds * (2 ** max(attempt - 1, 0)),
        )
        digest = hashlib.sha256(f"{delivery_id}:{handler}:{attempt}".encode()).digest()
        jitter_fraction = int.from_bytes(digest[:2], "big") / 65535
        return min(self.max_backoff_seconds, base + base * 0.1 * jitter_fraction)

    def complete_claim(
        self,
        claim: HandlerClaim,
        *,
        success: bool,
        transient: bool = False,
        error_code: str | None = None,
        now: datetime,
    ) -> HandlerStatus:
        if not success:
            if error_code is None or ERROR_CODE_RE.fullmatch(error_code) is None:
                raise ValueError("a bounded error_code is required for failures")
        now_text = self._iso(now)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT status, attempt, repository_id, delivery_id, handler, locked_by
                FROM github_webhook_outbox WHERE id=?
                """,
                (claim.claim_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError("claim not found")
            if row["status"] != "PROCESSING" or row["locked_by"] != claim.locked_by:
                connection.rollback()
                raise RuntimeError("claim is not owned by this worker")

            if success:
                new_status = HandlerStatus.SUCCEEDED
                connection.execute(
                    """
                    UPDATE github_webhook_outbox
                    SET status='SUCCEEDED', available_at=?, locked_at=NULL, locked_by=NULL,
                        last_error_code=NULL
                    WHERE id=?
                    """,
                    (now_text, claim.claim_id),
                )
            elif transient and int(row["attempt"]) < self.max_attempts:
                new_status = HandlerStatus.RETRY
                delay = self._retry_delay_seconds(
                    row["delivery_id"], row["handler"], int(row["attempt"])
                )
                available_at = self._iso(now + timedelta(seconds=delay))
                connection.execute(
                    """
                    UPDATE github_webhook_outbox
                    SET status='RETRY', available_at=?, locked_at=NULL, locked_by=NULL,
                        last_error_code=?
                    WHERE id=?
                    """,
                    (available_at, error_code, claim.claim_id),
                )
            else:
                new_status = HandlerStatus.DEAD_LETTER
                connection.execute(
                    """
                    UPDATE github_webhook_outbox
                    SET status='DEAD_LETTER', available_at=?, locked_at=NULL, locked_by=NULL,
                        last_error_code=?
                    WHERE id=?
                    """,
                    (now_text, error_code, claim.claim_id),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO github_webhook_dead_letters(
                        repository_id, delivery_id, handler, attempt, error_code, created_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        row["repository_id"],
                        row["delivery_id"],
                        row["handler"],
                        row["attempt"],
                        error_code,
                        now_text,
                    ),
                )
                previous = connection.execute(
                    """
                    SELECT status FROM github_webhook_deliveries
                    WHERE repository_id=? AND delivery_id=?
                    """,
                    (row["repository_id"], row["delivery_id"]),
                ).fetchone()["status"]
                connection.execute(
                    """
                    UPDATE github_webhook_deliveries
                    SET status='DEAD_LETTER', attempt=?, last_error_code=?
                    WHERE repository_id=? AND delivery_id=?
                    """,
                    (
                        row["attempt"],
                        error_code,
                        row["repository_id"],
                        row["delivery_id"],
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO github_webhook_status_history(
                        repository_id, delivery_id, from_status, to_status,
                        reason_code, changed_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        row["repository_id"],
                        row["delivery_id"],
                        previous,
                        "DEAD_LETTER",
                        error_code,
                        now_text,
                    ),
                )

            if success:
                pending = connection.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM github_webhook_outbox
                    WHERE repository_id=? AND delivery_id=? AND status!='SUCCEEDED'
                    """,
                    (row["repository_id"], row["delivery_id"]),
                ).fetchone()["n"]
                if pending == 0:
                    previous = connection.execute(
                        """
                        SELECT status FROM github_webhook_deliveries
                        WHERE repository_id=? AND delivery_id=?
                        """,
                        (row["repository_id"], row["delivery_id"]),
                    ).fetchone()["status"]
                    connection.execute(
                        """
                        UPDATE github_webhook_deliveries
                        SET status='PROCESSED', attempt=?, last_error_code=NULL
                        WHERE repository_id=? AND delivery_id=?
                        """,
                        (
                            row["attempt"],
                            row["repository_id"],
                            row["delivery_id"],
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO github_webhook_status_history(
                            repository_id, delivery_id, from_status, to_status,
                            reason_code, changed_at
                        ) VALUES(?,?,?,?,?,?)
                        """,
                        (
                            row["repository_id"],
                            row["delivery_id"],
                            previous,
                            "PROCESSED",
                            "ALL_HANDLERS_SUCCEEDED",
                            now_text,
                        ),
                    )
            connection.commit()
        return new_status

    def recover_processing(self, *, before: datetime, now: datetime) -> int:
        before_text = self._iso(before)
        now_text = self._iso(now)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE github_webhook_outbox
                SET status='RETRY', available_at=?, locked_at=NULL, locked_by=NULL,
                    last_error_code='WORKER_LEASE_EXPIRED'
                WHERE status='PROCESSING' AND locked_at < ?
                """,
                (now_text, before_text),
            )
            connection.commit()
            return int(cursor.rowcount)

    def health(self) -> bool:
        try:
            with self._connect() as connection:
                row = connection.execute("SELECT 1 AS ok").fetchone()
            return row["ok"] == 1
        except sqlite3.Error:
            return False

    def queue_depth(self) -> int:
        with self._connect() as connection:
            return int(
                connection.execute(
                    """
                    SELECT COUNT(*) AS n FROM github_webhook_outbox
                    WHERE status IN ('PENDING','PROCESSING','RETRY')
                    """
                ).fetchone()["n"]
            )

    def delivery_count(self) -> int:
        with self._connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) AS n FROM github_webhook_deliveries"
                ).fetchone()["n"]
            )

    def outbox_count(self) -> int:
        with self._connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) AS n FROM github_webhook_outbox"
                ).fetchone()["n"]
            )

    def dead_letter_count(self) -> int:
        with self._connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) AS n FROM github_webhook_dead_letters"
                ).fetchone()["n"]
            )

    def get_delivery(self, repository_id: int, delivery_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM github_webhook_deliveries
                WHERE repository_id=? AND delivery_id=?
                """,
                (repository_id, delivery_id),
            ).fetchone()
        return None if row is None else dict(row)

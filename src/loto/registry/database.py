from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class Database:
    """Small DB-API abstraction supporting SQLite and optional PostgreSQL."""

    def __init__(self, url: str):
        self.url = url
        self.kind = "postgres" if url.startswith(("postgres://", "postgresql://")) else "sqlite"
        if self.kind == "sqlite":
            raw = url.removeprefix("sqlite:///")
            self.path = Path(raw)
            self.path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self.path = None

    @contextlib.contextmanager
    def connect(self) -> Iterator[Any]:
        if self.kind == "sqlite":
            con = sqlite3.connect(self.path)
            con.row_factory = sqlite3.Row
        else:
            try:
                import psycopg
            except ImportError as exc:
                raise RuntimeError("PostgreSQL URL requires psycopg[binary]") from exc
            con = psycopg.connect(self.url)
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    @property
    def placeholder(self) -> str:
        return "%s" if self.kind == "postgres" else "?"

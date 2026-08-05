from __future__ import annotations

from pathlib import Path

from .postgres_store import PostgresMemoryStore
from .sqlite_store import SQLiteMemoryStore


def create_memory_store(location: str):
    if location.startswith(("postgres://", "postgresql://")):
        return PostgresMemoryStore(location)
    if location.startswith("sqlite:///"):
        location = location.removeprefix("sqlite:///")
    return SQLiteMemoryStore(Path(location))

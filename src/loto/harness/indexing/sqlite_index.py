from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..security import sha256_bytes
from .python_ast import parse_python_file

_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS code_files (
    path TEXT PRIMARY KEY,
    content_sha256 TEXT NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS code_symbols (
    symbol_id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    signature TEXT NOT NULL,
    docstring TEXT,
    calls_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    UNIQUE(path, qualified_name, start_line)
);
CREATE INDEX IF NOT EXISTS code_symbols_name_idx ON code_symbols(qualified_name);
CREATE INDEX IF NOT EXISTS code_symbols_path_idx ON code_symbols(path);
"""


class SQLiteCodeIndex:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(_SCHEMA)

    def index_repository(self, root: str | Path) -> dict[str, int]:
        root_path = Path(root).resolve()
        indexed_files = 0
        indexed_symbols = 0
        skipped_files = 0
        for path in sorted(root_path.rglob("*.py")):
            excluded = {
                ".git",
                ".venv",
                "venv",
                "site-packages",
                "artifacts",
                "runs",
            }
            if any(part in excluded for part in path.parts):
                continue
            relative = path.relative_to(root_path).as_posix()
            raw = path.read_bytes()
            digest = sha256_bytes(raw)
            existing = self.connection.execute(
                "SELECT content_sha256 FROM code_files WHERE path = ?", (relative,)
            ).fetchone()
            if existing and existing["content_sha256"] == digest:
                skipped_files += 1
                continue
            try:
                symbols = parse_python_file(path, root_path)
            except (SyntaxError, UnicodeDecodeError):
                skipped_files += 1
                continue
            with self.connection:
                self.connection.execute("DELETE FROM code_symbols WHERE path = ?", (relative,))
                self.connection.execute(
                    """
                    INSERT INTO code_files(path, content_sha256) VALUES (?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        content_sha256 = excluded.content_sha256,
                        indexed_at = CURRENT_TIMESTAMP
                    """,
                    (relative, digest),
                )
                for symbol in symbols:
                    self.connection.execute(
                        """
                        INSERT INTO code_symbols(
                            path, qualified_name, kind, start_line, end_line,
                            signature, docstring, calls_json, content_sha256
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            symbol.path,
                            symbol.qualified_name,
                            symbol.kind,
                            symbol.start_line,
                            symbol.end_line,
                            symbol.signature,
                            symbol.docstring,
                            json.dumps(symbol.calls, ensure_ascii=False),
                            symbol.content_sha256,
                        ),
                    )
            indexed_files += 1
            indexed_symbols += len(symbols)
        return {
            "indexed_files": indexed_files,
            "indexed_symbols": indexed_symbols,
            "skipped_files": skipped_files,
        }

    def search(self, query: str, limit: int = 20) -> list[dict]:
        escaped = f"%{query.replace('%', '')}%"
        rows = self.connection.execute(
            """
            SELECT * FROM code_symbols
            WHERE qualified_name LIKE ? OR signature LIKE ? OR path LIKE ?
                OR docstring LIKE ? OR calls_json LIKE ?
            ORDER BY
                CASE WHEN qualified_name = ? THEN 0
                     WHEN qualified_name LIKE ? THEN 1
                     ELSE 2 END,
                path, start_line
            LIMIT ?
            """,
            (escaped, escaped, escaped, escaped, escaped, query, escaped, limit),
        ).fetchall()
        return [
            {
                **dict(row),
                "calls": json.loads(row["calls_json"]),
            }
            for row in rows
        ]

    def close(self) -> None:
        self.connection.close()

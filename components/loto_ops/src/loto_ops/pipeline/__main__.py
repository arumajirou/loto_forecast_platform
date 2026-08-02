"""Create tables defined in docs/06_DB_SCHEMA.md"""

import sqlite3

DB_PATH = "loto_ops.db"

# テーブル作成SQL
CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    manifest TEXT
);

CREATE TABLE IF NOT EXISTS workflow_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    stage TEXT,
    status TEXT,
    duration_seconds REAL,
    details TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    artifact_name TEXT,
    artifact_type TEXT,
    file_path TEXT,
    size_bytes INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quality_checks (
    check_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    check_type TEXT,
    passed BOOLEAN,
    score REAL,
    details TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notifications (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    notification_type TEXT,
    message TEXT,
    sent_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.executescript(CREATE_TABLES)
conn.commit()
conn.close()
print("Tables created successfully in", DB_PATH)

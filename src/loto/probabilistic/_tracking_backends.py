from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from loto.observability.mlflow_bridge import MlflowBridge

_TABLES = ("runs", "metrics", "predictions", "artifacts")


def write_parquet(
    root: Path,
    run_record: dict[str, Any],
    frames: dict[str, pd.DataFrame],
) -> tuple[str, int]:
    target = root / "tracking" / "parquet"
    target.mkdir(parents=True, exist_ok=True)
    payload = {"runs": pd.DataFrame([run_record]), **frames}
    for name in _TABLES:
        payload[name].to_parquet(target / f"{name}.parquet", index=False)
    return target.as_uri(), sum(len(frame) for frame in payload.values())


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        output.append(
            {
                key: (None if pd.isna(value) else value)
                for key, value in row.items()
            }
        )
    return output


def write_duckdb(
    path: Path,
    run_record: dict[str, Any],
    frames: dict[str, pd.DataFrame],
) -> tuple[str, int]:
    import duckdb

    path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(path))
    try:
        connection.execute("BEGIN TRANSACTION")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS ppl02_runs (
            run_id VARCHAR PRIMARY KEY, created_at VARCHAR, model_id VARCHAR,
            model_revision VARCHAR, game VARCHAR, status VARCHAR,
            config_hash VARCHAR, data_hash VARCHAR, code_hash VARCHAR,
            git_commit VARCHAR, prediction_payload_sha256 VARCHAR,
            artifact_uri VARCHAR, record_json VARCHAR)"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS ppl02_metrics (
            run_id VARCHAR, row_kind VARCHAR, baseline VARCHAR, seed BIGINT,
            cutoff BIGINT, draw_id VARCHAR, metric_name VARCHAR, metric_value DOUBLE)"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS ppl02_predictions (
            run_id VARCHAR, row_kind VARCHAR, baseline VARCHAR, seed BIGINT,
            cutoff BIGINT, draw_id VARCHAR, prediction_json VARCHAR,
            actual_json VARCHAR, candidate_marginals_json VARCHAR,
            actual_known BOOLEAN, prediction_payload_sha256 VARCHAR)"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS ppl02_artifacts (
            run_id VARCHAR, path VARCHAR, size BIGINT, sha256 VARCHAR)"""
        )
        connection.execute("DELETE FROM ppl02_runs WHERE run_id = ?", [run_record["run_id"]])
        connection.execute(
            "INSERT INTO ppl02_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_record.get(key)
                for key in (
                    "run_id", "created_at", "model_id", "model_revision", "game",
                    "status", "config_hash", "data_hash", "code_hash", "git_commit",
                    "prediction_payload_sha256", "artifact_uri",
                )
            ]
            + [json.dumps(run_record, ensure_ascii=False, default=str)],
        )
        for table, frame in frames.items():
            connection.execute(f"DELETE FROM ppl02_{table} WHERE run_id = ?", [run_record["run_id"]])
            if not frame.empty:
                connection.register("incoming", frame)
                connection.execute(f"INSERT INTO ppl02_{table} SELECT * FROM incoming")
                connection.unregister("incoming")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    return path.resolve().as_uri(), 1 + sum(len(frame) for frame in frames.values())


def write_postgres(
    dsn: str,
    run_record: dict[str, Any],
    frames: dict[str, pd.DataFrame],
) -> tuple[str, int]:
    from sqlalchemy import create_engine, text

    engine = create_engine(dsn, future=True)
    ddl = {
        "runs": """CREATE TABLE IF NOT EXISTS ppl02_runs (
        run_id TEXT PRIMARY KEY, created_at TEXT, model_id TEXT, model_revision TEXT,
        game TEXT, status TEXT, config_hash TEXT, data_hash TEXT, code_hash TEXT,
        git_commit TEXT, prediction_payload_sha256 TEXT, artifact_uri TEXT,
        record_json JSONB)""",
        "metrics": """CREATE TABLE IF NOT EXISTS ppl02_metrics (
        run_id TEXT, row_kind TEXT, baseline TEXT, seed BIGINT, cutoff BIGINT,
        draw_id TEXT, metric_name TEXT, metric_value DOUBLE PRECISION)""",
        "predictions": """CREATE TABLE IF NOT EXISTS ppl02_predictions (
        run_id TEXT, row_kind TEXT, baseline TEXT, seed BIGINT, cutoff BIGINT,
        draw_id TEXT, prediction_json TEXT, actual_json TEXT,
        candidate_marginals_json TEXT, actual_known BOOLEAN,
        prediction_payload_sha256 TEXT)""",
        "artifacts": """CREATE TABLE IF NOT EXISTS ppl02_artifacts (
        run_id TEXT, path TEXT, size BIGINT, sha256 TEXT)""",
    }
    with engine.begin() as connection:
        for statement in ddl.values():
            connection.execute(text(statement))
        for table in _TABLES:
            connection.execute(text(f"DELETE FROM ppl02_{table} WHERE run_id = :run_id"), {"run_id": run_record["run_id"]})
        record = dict(run_record)
        record["record_json"] = json.dumps(run_record, ensure_ascii=False, default=str)
        columns = [
            "run_id", "created_at", "model_id", "model_revision", "game", "status",
            "config_hash", "data_hash", "code_hash", "git_commit",
            "prediction_payload_sha256", "artifact_uri", "record_json",
        ]
        connection.execute(
            text(f"INSERT INTO ppl02_runs ({','.join(columns)}) VALUES ({','.join(':'+c for c in columns)})"),
            {key: record.get(key) for key in columns},
        )
        for table, frame in frames.items():
            if not frame.empty:
                frame.to_sql(f"ppl02_{table}", connection, if_exists="append", index=False, method="multi")
    safe_uri = engine.url.render_as_string(hide_password=True)
    engine.dispose()
    return safe_uri, 1 + sum(len(frame) for frame in frames.values())


def write_mlflow(
    uri: str,
    experiment: str,
    run_record: dict[str, Any],
    metrics: dict[str, float],
    root: Path,
) -> tuple[str, int]:
    params = {
        key: run_record[key]
        for key in (
            "run_id", "model_id", "model_revision", "game", "status",
            "config_hash", "data_hash", "code_hash", "git_commit",
            "prediction_payload_sha256",
        )
    }
    response = MlflowBridge(uri, experiment).record_run(
        run_record["run_id"], params, metrics, [str(root)]
    )
    if not response.get("enabled"):
        raise RuntimeError(str(response.get("reason", "mlflow_recording_failed")))
    return f"{uri}#{response['run_id']}", 1

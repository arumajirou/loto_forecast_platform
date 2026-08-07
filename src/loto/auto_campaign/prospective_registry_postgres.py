"""PostgreSQL transaction phases for Prospective registration."""

from __future__ import annotations

import json
import time
from typing import Any

import pandas as pd

POSTGRES_TABLES = (
    "nf_prospective_registry_runs",
    "nf_prospective_registry_candidates",
    "nf_prospective_registry_seed_metrics",
    "nf_prospective_registry_position_metrics",
    "nf_prospective_registry_artifacts",
)


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        output.append(
            {
                key: None if pd.isna(value) else value
                for key, value in row.items()
            }
        )
    return output


def _ddl() -> tuple[str, ...]:
    return (
        """CREATE TABLE IF NOT EXISTS nf_prospective_registry_runs (
        registry_id TEXT PRIMARY KEY,
        scoring_id TEXT NOT NULL,
        registry_namespace TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        source_run_id TEXT,
        prediction_lock_sha256 TEXT NOT NULL,
        scoring_report_sha256 TEXT NOT NULL,
        artifact_manifest_sha256 TEXT NOT NULL,
        scoring_sha256s_sha256 TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        mlflow_tracking_uri TEXT,
        mlflow_experiment TEXT,
        mlflow_parent_run_id TEXT,
        record_json JSONB NOT NULL,
        backend_receipt_json JSONB,
        error_json JSONB,
        UNIQUE (scoring_id, registry_namespace)
        )""",
        """CREATE TABLE IF NOT EXISTS nf_prospective_registry_candidates (
        registry_id TEXT NOT NULL REFERENCES nf_prospective_registry_runs(registry_id),
        candidate_key TEXT NOT NULL,
        source_type TEXT NOT NULL,
        model_name TEXT,
        baseline_name TEXT,
        track TEXT,
        seed_count BIGINT,
        hit_pm1_mean DOUBLE PRECISION,
        hit_pm1_var DOUBLE PRECISION,
        hit_pm1_min DOUBLE PRECISION,
        hit_pm1_max DOUBLE PRECISION,
        all_positions_hit_pm1_mean DOUBLE PRECISION,
        mae_mean DOUBLE PRECISION,
        mse_mean DOUBLE PRECISION,
        rmse_mean DOUBLE PRECISION,
        worst_seed_hit_pm1 DOUBLE PRECISION,
        rank BIGINT,
        record_json JSONB NOT NULL,
        PRIMARY KEY (registry_id, candidate_key)
        )""",
        """CREATE TABLE IF NOT EXISTS nf_prospective_registry_seed_metrics (
        registry_id TEXT NOT NULL REFERENCES nf_prospective_registry_runs(registry_id),
        candidate_key TEXT NOT NULL,
        seed_token TEXT NOT NULL,
        seed BIGINT,
        hit_pm1 DOUBLE PRECISION,
        all_positions_hit_pm1 DOUBLE PRECISION,
        mae DOUBLE PRECISION,
        mse DOUBLE PRECISION,
        rmse DOUBLE PRECISION,
        record_json JSONB NOT NULL,
        PRIMARY KEY (registry_id, candidate_key, seed_token)
        )""",
        """CREATE TABLE IF NOT EXISTS nf_prospective_registry_position_metrics (
        registry_id TEXT NOT NULL REFERENCES nf_prospective_registry_runs(registry_id),
        row_key TEXT NOT NULL,
        candidate_key TEXT NOT NULL,
        seed_token TEXT NOT NULL,
        unique_id TEXT,
        variant TEXT,
        hit_pm1 DOUBLE PRECISION,
        exact_hit DOUBLE PRECISION,
        mae DOUBLE PRECISION,
        mse DOUBLE PRECISION,
        rmse DOUBLE PRECISION,
        record_json JSONB NOT NULL,
        PRIMARY KEY (registry_id, row_key)
        )""",
        """CREATE TABLE IF NOT EXISTS nf_prospective_registry_artifacts (
        registry_id TEXT NOT NULL REFERENCES nf_prospective_registry_runs(registry_id),
        path TEXT NOT NULL,
        size_bytes BIGINT NOT NULL,
        sha256 TEXT NOT NULL,
        PRIMARY KEY (registry_id, path)
        )""",
    )


def _run_record(payload: dict[str, Any], status: str) -> dict[str, Any]:
    source = payload["source"]
    backends = payload["backend_policy"]
    return {
        "registry_id": payload["registry_id"],
        "scoring_id": payload["scoring_id"],
        "registry_namespace": payload["registry_namespace"],
        "status": status,
        "created_at": payload["created_at"],
        "updated_at": payload["created_at"],
        "source_run_id": source.get("source_run_id"),
        "prediction_lock_sha256": source["prediction_lock_sha256"],
        "scoring_report_sha256": source["scoring_report_sha256"],
        "artifact_manifest_sha256": source["artifact_manifest_sha256"],
        "scoring_sha256s_sha256": source["scoring_sha256s_sha256"],
        "payload_sha256": payload["payload_sha256"],
        "mlflow_tracking_uri": backends["mlflow_tracking_uri"],
        "mlflow_experiment": backends["mlflow_experiment"],
        "mlflow_parent_run_id": None,
        "record_json": _json(payload),
        "backend_receipt_json": None,
        "error_json": None,
    }


def prepare_postgres(
    dsn: str,
    payload: dict[str, Any],
    frames: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    """Create or refresh a fail-closed PostgreSQL registration transaction."""

    from sqlalchemy import create_engine, text

    engine = create_engine(dsn, future=True)
    started = time.perf_counter()
    run = _run_record(payload, "PENDING_MLFLOW")
    try:
        with engine.begin() as connection:
            for statement in _ddl():
                connection.execute(text(statement))
            existing = connection.execute(
                text(
                    "SELECT payload_sha256 FROM nf_prospective_registry_runs "
                    "WHERE registry_id = :registry_id"
                ),
                {"registry_id": payload["registry_id"]},
            ).scalar_one_or_none()
            if existing is not None and str(existing) != payload["payload_sha256"]:
                raise ValueError(
                    "registry_id already exists with a different payload SHA-256"
                )
            if existing is None:
                connection.execute(
                    text(
                        """INSERT INTO nf_prospective_registry_runs (
                        registry_id, scoring_id, registry_namespace, status, created_at, updated_at,
                        source_run_id, prediction_lock_sha256,
                        scoring_report_sha256, artifact_manifest_sha256,
                        scoring_sha256s_sha256, payload_sha256,
                        mlflow_tracking_uri, mlflow_experiment,
                        mlflow_parent_run_id, record_json,
                        backend_receipt_json, error_json
                        ) VALUES (
                        :registry_id, :scoring_id, :registry_namespace, :status,
                        :created_at, :updated_at,
                        :source_run_id, :prediction_lock_sha256,
                        :scoring_report_sha256, :artifact_manifest_sha256,
                        :scoring_sha256s_sha256, :payload_sha256,
                        :mlflow_tracking_uri, :mlflow_experiment,
                        :mlflow_parent_run_id, CAST(:record_json AS JSONB),
                        NULL, NULL
                        )"""
                    ),
                    run,
                )
            else:
                connection.execute(
                    text(
                        """UPDATE nf_prospective_registry_runs SET
                        status = :status,
                        updated_at = :updated_at,
                        source_run_id = :source_run_id,
                        prediction_lock_sha256 = :prediction_lock_sha256,
                        scoring_report_sha256 = :scoring_report_sha256,
                        artifact_manifest_sha256 = :artifact_manifest_sha256,
                        scoring_sha256s_sha256 = :scoring_sha256s_sha256,
                        mlflow_tracking_uri = :mlflow_tracking_uri,
                        mlflow_experiment = :mlflow_experiment,
                        record_json = CAST(:record_json AS JSONB),
                        backend_receipt_json = NULL,
                        error_json = NULL
                        WHERE registry_id = :registry_id"""
                    ),
                    run,
                )

            table_map = {
                "candidates": "nf_prospective_registry_candidates",
                "seed_metrics": "nf_prospective_registry_seed_metrics",
                "position_metrics": "nf_prospective_registry_position_metrics",
                "artifacts": "nf_prospective_registry_artifacts",
            }
            for frame_name, table_name in table_map.items():
                connection.execute(
                    text(f"DELETE FROM {table_name} WHERE registry_id = :registry_id"),
                    {"registry_id": payload["registry_id"]},
                )
                records = _records(frames[frame_name])
                if not records:
                    continue
                if frame_name == "candidates":
                    statement = text(
                        """INSERT INTO nf_prospective_registry_candidates (
                        registry_id, candidate_key, source_type, model_name,
                        baseline_name, track, seed_count, hit_pm1_mean,
                        hit_pm1_var, hit_pm1_min, hit_pm1_max,
                        all_positions_hit_pm1_mean, mae_mean, mse_mean,
                        rmse_mean, worst_seed_hit_pm1, rank, record_json
                        ) VALUES (
                        :registry_id, :candidate_key, :source_type, :model_name,
                        :baseline_name, :track, :seed_count, :hit_pm1_mean,
                        :hit_pm1_var, :hit_pm1_min, :hit_pm1_max,
                        :all_positions_hit_pm1_mean, :mae_mean, :mse_mean,
                        :rmse_mean, :worst_seed_hit_pm1, :rank,
                        CAST(:record_json AS JSONB)
                        )"""
                    )
                elif frame_name == "seed_metrics":
                    statement = text(
                        """INSERT INTO nf_prospective_registry_seed_metrics (
                        registry_id, candidate_key, seed_token, seed,
                        hit_pm1, all_positions_hit_pm1, mae, mse, rmse,
                        record_json
                        ) VALUES (
                        :registry_id, :candidate_key, :seed_token, :seed,
                        :hit_pm1, :all_positions_hit_pm1, :mae, :mse, :rmse,
                        CAST(:record_json AS JSONB)
                        )"""
                    )
                elif frame_name == "position_metrics":
                    statement = text(
                        """INSERT INTO nf_prospective_registry_position_metrics (
                        registry_id, row_key, candidate_key, seed_token,
                        unique_id, variant, hit_pm1, exact_hit, mae, mse, rmse,
                        record_json
                        ) VALUES (
                        :registry_id, :row_key, :candidate_key, :seed_token,
                        :unique_id, :variant, :hit_pm1, :exact_hit,
                        :mae, :mse, :rmse, CAST(:record_json AS JSONB)
                        )"""
                    )
                else:
                    statement = text(
                        """INSERT INTO nf_prospective_registry_artifacts (
                        registry_id, path, size_bytes, sha256
                        ) VALUES (
                        :registry_id, :path, :size_bytes, :sha256
                        )"""
                    )
                connection.execute(statement, records)
    finally:
        safe_uri = engine.url.render_as_string(hide_password=True)
        engine.dispose()
    return {
        "backend": "postgres",
        "status": "PASS",
        "phase": "PREPARED",
        "safe_uri": safe_uri,
        "registry_id": payload["registry_id"],
        "records": 1 + sum(len(frame) for frame in frames.values()),
        "duration_seconds": time.perf_counter() - started,
    }


def finalize_postgres(
    dsn: str,
    payload: dict[str, Any],
    mlflow_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Finalize a prepared PostgreSQL row after MLflow succeeds."""

    from sqlalchemy import create_engine, text

    engine = create_engine(dsn, future=True)
    started = time.perf_counter()
    try:
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    """UPDATE nf_prospective_registry_runs SET
                    status = 'PASS',
                    updated_at = :updated_at,
                    mlflow_parent_run_id = :mlflow_parent_run_id,
                    backend_receipt_json = CAST(:receipt AS JSONB),
                    error_json = NULL
                    WHERE registry_id = :registry_id
                    AND payload_sha256 = :payload_sha256"""
                ),
                {
                    "updated_at": payload["created_at"],
                    "mlflow_parent_run_id": mlflow_receipt["parent_run_id"],
                    "receipt": _json(mlflow_receipt),
                    "registry_id": payload["registry_id"],
                    "payload_sha256": payload["payload_sha256"],
                },
            )
            if result.rowcount != 1:
                raise ValueError("prepared PostgreSQL registry row was not found")
    finally:
        safe_uri = engine.url.render_as_string(hide_password=True)
        engine.dispose()
    return {
        "backend": "postgres",
        "status": "PASS",
        "phase": "FINALIZED",
        "safe_uri": safe_uri,
        "registry_id": payload["registry_id"],
        "mlflow_parent_run_id": mlflow_receipt["parent_run_id"],
        "duration_seconds": time.perf_counter() - started,
    }


def mark_postgres_blocked(
    dsn: str,
    payload: dict[str, Any],
    error: dict[str, Any],
) -> dict[str, Any]:
    """Best-effort durable failure transition for a prepared row."""

    from sqlalchemy import create_engine, text

    engine = create_engine(dsn, future=True)
    try:
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    """UPDATE nf_prospective_registry_runs SET
                    status = 'BLOCKED',
                    updated_at = :updated_at,
                    error_json = CAST(:error AS JSONB)
                    WHERE registry_id = :registry_id
                    AND payload_sha256 = :payload_sha256"""
                ),
                {
                    "updated_at": payload["created_at"],
                    "error": _json(error),
                    "registry_id": payload["registry_id"],
                    "payload_sha256": payload["payload_sha256"],
                },
            )
            updated = int(result.rowcount or 0)
    finally:
        safe_uri = engine.url.render_as_string(hide_password=True)
        engine.dispose()
    return {
        "backend": "postgres",
        "status": "PASS" if updated == 1 else "NOT_PREPARED",
        "phase": "MARKED_BLOCKED",
        "safe_uri": safe_uri,
        "registry_id": payload["registry_id"],
        "updated_rows": updated,
    }

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Mapping

import pandas as pd

from loto.data.lineage import (
    artifact_descriptor,
    atomic_write_frame_csv,
    atomic_write_json,
    frame_fingerprint,
)


def write_dataset_bundle(
    tables: Mapping[str, pd.DataFrame],
    output_dir: str | Path,
    *,
    sqlite_name: str = "datasets.sqlite3",
    parquet: bool = True,
    require_parquet: bool = False,
) -> dict:
    """Atomically persist CSV/SQLite and optionally Parquet with explicit status.

    Parquet failures are represented in the manifest. They are raised only when
    ``require_parquet`` is true; this prevents silent artifact loss while keeping
    the core installation dependency-light.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    sqlite_path = out / sqlite_name
    fd, tmp_name = tempfile.mkstemp(prefix=f".{sqlite_name}.", suffix=".tmp", dir=out)
    os.close(fd)
    Path(tmp_name).unlink(missing_ok=True)
    manifest: dict[str, dict] = {}
    parquet_errors: list[str] = []
    try:
        with contextlib.closing(sqlite3.connect(tmp_name)) as conn:
            for name, frame in tables.items():
                frame.to_sql(name, conn, if_exists="replace", index=False)
                csv_path = atomic_write_frame_csv(frame, out / f"{name}.csv")
                entry: dict = {
                    "rows": int(len(frame)),
                    "columns": list(frame.columns),
                    "dtypes": {col: str(dtype) for col, dtype in frame.dtypes.items()},
                    "frame_sha256": frame_fingerprint(frame),
                    "sqlite_table": name,
                    "csv": artifact_descriptor(csv_path),
                    "parquet": {"enabled": parquet, "status": "SKIPPED" if not parquet else "PENDING"},
                }
                if parquet:
                    parquet_path = out / f"{name}.parquet"
                    parquet_tmp = parquet_path.with_suffix(".parquet.tmp")
                    try:
                        frame.to_parquet(parquet_tmp, index=False)
                        parquet_tmp.replace(parquet_path)
                        entry["parquet"] = {"enabled": True, "status": "WRITTEN", **artifact_descriptor(parquet_path)}
                    except Exception as exc:  # availability is recorded, never hidden
                        parquet_tmp.unlink(missing_ok=True)
                        detail = f"{name}:{type(exc).__name__}:{exc}"
                        parquet_errors.append(detail)
                        entry["parquet"] = {"enabled": True, "status": "FAILED", "error": detail}
                manifest[name] = entry
            conn.commit()
        Path(tmp_name).replace(sqlite_path)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    if require_parquet and parquet_errors:
        raise RuntimeError("Parquet artifacts required but failed: " + "; ".join(parquet_errors))
    payload = {
        "schema_version": "2.1.0",
        "sqlite": artifact_descriptor(sqlite_path),
        "tables": manifest,
        "parquet_errors": parquet_errors,
    }
    manifest_path = atomic_write_json(out / "dataset_bundle_manifest.json", payload)
    return {"sqlite": str(sqlite_path), "manifest": str(manifest_path), "tables": manifest, "parquet_errors": parquet_errors}


def copy_bundle_to_postgres(
    tables: Mapping[str, pd.DataFrame],
    dsn: str,
    *,
    schema: str = "dataset",
    if_exists: str = "replace",
) -> dict:
    try:
        from sqlalchemy import create_engine, text
    except ImportError as exc:
        raise RuntimeError("PostgreSQL export requires the full/postgres extra") from exc
    engine = create_engine(dsn, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        written = {}
        for name, frame in tables.items():
            frame.to_sql(name, engine, schema=schema, if_exists=if_exists, index=False, method="multi", chunksize=5000)
            written[f"{schema}.{name}"] = int(len(frame))
        return written
    finally:
        engine.dispose()

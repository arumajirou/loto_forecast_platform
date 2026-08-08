"""Read-only PostgreSQL and MLflow probes for registry reconciliation."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from .persistence import sha256_file
from .prospective_registry_mlflow import redact_uri


def _mapping(row: Any) -> dict[str, Any]:
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return dict(row)


def query_postgres(dsn: str, expected: dict[str, Any]) -> dict[str, Any]:
    """Read one registry and its child tables without modifying PostgreSQL."""

    from sqlalchemy import create_engine, text

    started = time.perf_counter()
    engine = create_engine(dsn, future=True)
    registry_id = expected["registry_id"]
    try:
        with engine.connect() as connection:
            run_rows = connection.execute(
                text("SELECT * FROM nf_prospective_registry_runs WHERE registry_id = :registry_id"),
                {"registry_id": registry_id},
            ).fetchall()
            queries = {
                "candidates": (
                    "SELECT * FROM nf_prospective_registry_candidates "
                    "WHERE registry_id = :registry_id ORDER BY candidate_key"
                ),
                "seed_metrics": (
                    "SELECT * FROM nf_prospective_registry_seed_metrics "
                    "WHERE registry_id = :registry_id "
                    "ORDER BY candidate_key, seed_token"
                ),
                "position_metrics": (
                    "SELECT * FROM nf_prospective_registry_position_metrics "
                    "WHERE registry_id = :registry_id ORDER BY row_key"
                ),
                "artifacts": (
                    "SELECT * FROM nf_prospective_registry_artifacts "
                    "WHERE registry_id = :registry_id ORDER BY path"
                ),
            }
            children = {
                name: [
                    _mapping(row)
                    for row in connection.execute(
                        text(statement),
                        {"registry_id": registry_id},
                    ).fetchall()
                ]
                for name, statement in queries.items()
            }
    finally:
        safe_uri = engine.url.render_as_string(hide_password=True)
        engine.dispose()
    return {
        "backend": "postgres",
        "status": "PASS",
        "safe_uri": safe_uri,
        "registry_id": registry_id,
        "run_rows": [_mapping(row) for row in run_rows],
        **children,
        "duration_seconds": time.perf_counter() - started,
    }


def _runs(client: Any, experiment_id: str, registry_id: str, role: str) -> list[Any]:
    return list(
        client.search_runs(
            [experiment_id],
            filter_string=(f"tags.registry_id = '{registry_id}' AND tags.registry_role = '{role}'"),
            max_results=100000,
        )
    )


def _run_snapshot(run: Any) -> dict[str, Any]:
    return {
        "run_id": str(run.info.run_id),
        "status": str(run.info.status),
        "experiment_id": str(run.info.experiment_id),
        "tags": dict(run.data.tags),
        "params": dict(run.data.params),
        "metrics": {key: float(value) for key, value in run.data.metrics.items()},
    }


def _download_sha256(
    client: Any,
    run_id: str,
    artifact_path: str,
    target: Path,
) -> dict[str, Any]:
    downloaded = Path(
        client.download_artifacts(
            run_id,
            artifact_path,
            str(target),
        )
    )
    if downloaded.is_dir():
        raise ValueError(f"expected MLflow artifact is a directory: {artifact_path}")
    if downloaded.is_symlink() or not downloaded.is_file():
        raise ValueError(f"MLflow artifact is not a regular file: {artifact_path}")
    return {
        "path": artifact_path,
        "sha256": sha256_file(downloaded),
        "size_bytes": downloaded.stat().st_size,
    }


def query_mlflow(
    tracking_uri: str,
    experiment_name: str,
    expected: dict[str, Any],
    *,
    require_remote_artifacts: bool,
) -> dict[str, Any]:
    """Read parent/child runs and selected immutable artifacts from MLflow."""

    import mlflow
    from mlflow import MlflowClient

    started = time.perf_counter()
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()
    experiment = client.get_experiment_by_name(experiment_name)
    if experiment is None:
        return {
            "backend": "mlflow",
            "status": "PASS",
            "safe_uri": redact_uri(tracking_uri),
            "experiment_name": experiment_name,
            "experiment_id": None,
            "parent_runs": [],
            "child_runs": [],
            "artifacts": [],
            "duration_seconds": time.perf_counter() - started,
        }
    experiment_id = str(experiment.experiment_id)
    parent_runs = _runs(
        client,
        experiment_id,
        expected["registry_id"],
        "parent",
    )
    child_runs = _runs(
        client,
        experiment_id,
        expected["registry_id"],
        "seed",
    )
    artifacts: list[dict[str, Any]] = []
    if require_remote_artifacts and len(parent_runs) == 1:
        parent_id = str(parent_runs[0].info.run_id)
        with tempfile.TemporaryDirectory(prefix="registry-reconcile-mlflow-") as temp:
            target = Path(temp)
            for item in expected["mlflow_artifacts"]:
                artifacts.append(
                    _download_sha256(
                        client,
                        parent_id,
                        str(item["path"]),
                        target,
                    )
                )
    return {
        "backend": "mlflow",
        "status": "PASS",
        "safe_uri": redact_uri(tracking_uri),
        "experiment_name": experiment_name,
        "experiment_id": experiment_id,
        "parent_runs": [_run_snapshot(run) for run in parent_runs],
        "child_runs": [_run_snapshot(run) for run in child_runs],
        "artifacts": artifacts,
        "duration_seconds": time.perf_counter() - started,
    }

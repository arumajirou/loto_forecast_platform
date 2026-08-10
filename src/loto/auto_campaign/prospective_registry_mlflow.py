"""MLflow parent and per-seed child runs for Prospective registration."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pandas as pd


def redact_uri(uri: str) -> str:
    """Return a URI safe for durable logs and receipts."""

    text = str(uri or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
        hostname = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        return "<redacted-uri>"
    if port is not None:
        hostname = f"{hostname}:{port}"
    netloc = hostname
    if parsed.username:
        netloc = f"{parsed.username}:***@{hostname}"
    safe_query = "&".join(
        f"{item.split('=', 1)[0]}=***" if "=" in item else item
        for item in parsed.query.split("&")
        if item
    )
    return urlunsplit(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            safe_query,
            "",
        )
    )


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        output.append({key: None if pd.isna(value) else value for key, value in row.items()})
    return output


def _experiment(client: Any, name: str) -> str:
    current = client.get_experiment_by_name(name)
    if current is not None:
        return str(current.experiment_id)
    return str(client.create_experiment(name))


def _find_run(
    client: Any,
    experiment_id: str,
    *,
    registry_id: str,
    role: str,
    candidate_key: str | None = None,
    seed_token: str | None = None,
) -> Any | None:
    filters = [
        f"tags.registry_id = '{registry_id}'",
        f"tags.registry_role = '{role}'",
    ]
    if candidate_key is not None:
        escaped = candidate_key.replace("'", "\\'")
        filters.append(f"tags.candidate_key = '{escaped}'")
    if seed_token is not None:
        filters.append(f"tags.seed_token = '{seed_token}'")
    runs = client.search_runs(
        [experiment_id],
        filter_string=" AND ".join(filters),
        max_results=2,
    )
    if len(runs) > 1:
        raise ValueError(f"multiple MLflow runs found for registry role={role}")
    return runs[0] if runs else None


def _safe_param(value: Any) -> str:
    return str(value)[:500]


def _metric_pairs(row: dict[str, Any]) -> dict[str, float]:
    names = (
        "hit_pm1",
        "all_positions_hit_pm1",
        "mae",
        "mse",
        "rmse",
    )
    result: dict[str, float] = {}
    for name in names:
        value = row.get(name)
        if value is not None and not pd.isna(value):
            result[name] = float(value)
    return result


def record_mlflow(
    tracking_uri: str,
    experiment_name: str,
    payload: dict[str, Any],
    frames: dict[str, pd.DataFrame],
    *,
    evidence_root: Path,
    scoring_root: Path,
    artifact_mode: str,
) -> dict[str, Any]:
    """Create or recover one parent run and per-seed child runs."""

    from mlflow.entities import Metric, Param

    import mlflow
    from mlflow import MlflowClient

    started = time.perf_counter()
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()
    experiment_id = _experiment(client, experiment_name)
    parent = _find_run(
        client,
        experiment_id,
        registry_id=payload["registry_id"],
        role="parent",
    )
    parent_reused = parent is not None
    if parent is None:
        parent = client.create_run(
            experiment_id,
            tags={
                "mlflow.runName": payload["registry_id"],
                "registry_id": payload["registry_id"],
                "registry_role": "parent",
                "payload_sha256": payload["payload_sha256"],
                "scoring_id": payload["scoring_id"],
            },
        )
    elif parent.data.tags.get("payload_sha256") != payload["payload_sha256"]:
        raise ValueError("existing MLflow parent run has a different payload SHA-256")
    parent_run_id = str(parent.info.run_id)

    report = payload["scoring_report"]
    source = payload["source"]
    parent_params = {
        "registry_id": payload["registry_id"],
        "scoring_id": payload["scoring_id"],
        "registry_namespace": payload["registry_namespace"],
        "source_run_id": source.get("source_run_id"),
        "prediction_lock_sha256": source["prediction_lock_sha256"],
        "scoring_report_sha256": source["scoring_report_sha256"],
        "artifact_manifest_sha256": source["artifact_manifest_sha256"],
        "payload_sha256": payload["payload_sha256"],
        "priority_metric": payload["metric_policy"]["priority_metric"],
        "candidate_count": payload["counts"]["candidate_count"],
        "seed_metric_rows": payload["counts"]["seed_metric_rows"],
        "artifact_mode": artifact_mode,
    }
    parent_metrics: dict[str, float] = {
        "candidate_count": float(payload["counts"]["candidate_count"]),
        "seed_metric_rows": float(payload["counts"]["seed_metric_rows"]),
        "position_metric_rows": float(payload["counts"]["position_metric_rows"]),
    }
    champion = report.get("champion")
    if isinstance(champion, dict):
        for name, value in champion.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                parent_metrics[f"champion_{name}"] = float(value)
    if parent.data.tags.get("registry_payload_logged") != "true":
        client.log_batch(
            parent_run_id,
            params=[Param(key, _safe_param(value)) for key, value in parent_params.items()],
            metrics=[
                Metric(
                    key,
                    value,
                    int(time.time() * 1000),
                    0,
                )
                for key, value in parent_metrics.items()
            ],
        )
        client.set_tag(parent_run_id, "registry_payload_logged", "true")

    child_ids: list[str] = []
    reused_children = 0
    for row in _records(frames["seed_metrics"]):
        existing = _find_run(
            client,
            experiment_id,
            registry_id=payload["registry_id"],
            role="seed",
            candidate_key=str(row["candidate_key"]),
            seed_token=str(row["seed_token"]),
        )
        if existing is None:
            child = client.create_run(
                experiment_id,
                tags={
                    "mlflow.runName": (f"{row['candidate_key']}:seed={row['seed_token']}")[:250],
                    "mlflow.parentRunId": parent_run_id,
                    "registry_id": payload["registry_id"],
                    "registry_role": "seed",
                    "candidate_key": str(row["candidate_key"]),
                    "seed_token": str(row["seed_token"]),
                    "payload_sha256": payload["payload_sha256"],
                },
            )
            child_id = str(child.info.run_id)
            params = {
                "source_type": row.get("source_type"),
                "model_name": row.get("model_name"),
                "baseline_name": row.get("baseline_name"),
                "track": row.get("track"),
                "seed": row.get("seed"),
            }
            client.log_batch(
                child_id,
                params=[Param(key, _safe_param(value)) for key, value in params.items()],
                metrics=[
                    Metric(
                        key,
                        value,
                        int(time.time() * 1000),
                        0,
                    )
                    for key, value in _metric_pairs(row).items()
                ],
            )
            client.set_terminated(child_id, status="FINISHED")
        else:
            if existing.data.tags.get("payload_sha256") != payload["payload_sha256"]:
                raise ValueError("existing MLflow child run has a different payload SHA-256")
            child_id = str(existing.info.run_id)
            reused_children += 1
        child_ids.append(child_id)

    refreshed_parent = client.get_run(parent_run_id)
    if refreshed_parent.data.tags.get("registry_artifacts_logged") != "true":
        client.log_artifacts(
            parent_run_id,
            str(evidence_root),
            artifact_path="registry_evidence",
        )
        if artifact_mode == "full":
            client.log_artifacts(
                parent_run_id,
                str(scoring_root),
                artifact_path="scoring_artifact",
            )
        client.set_tag(parent_run_id, "registry_artifacts_logged", "true")
        client.set_tag(parent_run_id, "artifact_mode", artifact_mode)
    client.set_terminated(parent_run_id, status="FINISHED")
    return {
        "backend": "mlflow",
        "status": "PASS",
        "safe_uri": redact_uri(tracking_uri),
        "experiment_name": experiment_name,
        "experiment_id": experiment_id,
        "parent_run_id": parent_run_id,
        "parent_reused": parent_reused,
        "child_run_ids": child_ids,
        "child_count": len(child_ids),
        "reused_child_count": reused_children,
        "artifact_mode": artifact_mode,
        "duration_seconds": time.perf_counter() - started,
    }

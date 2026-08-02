"""
nf_model_runs テーブルへの書き込みを担当するロガー。
"""

from __future__ import annotations

import json
import traceback
from typing import Any, Dict, Optional, Sequence

import psycopg2

from config.db_config import DB_CONFIG


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def log_run_start(
    table_name: str,
    loto: str,
    unique_ids: Sequence[str],
    model_name: str,
    backend: str,
    horizon: int,
    loss: str,
    metric: str,
    optimization_config: Dict[str, Any],
    search_space: Optional[Dict[str, Any]],
    resource_snapshot: Dict[str, Any],
    system_info: Optional[Dict[str, Any]] = None,
) -> int:
    """nf_model_runs に 1 レコード挿入し、run_id を返す。"""
    unique_ids_list = list(unique_ids)
    system_info = system_info or {}

    with get_connection() as conn:
        with conn.cursor() as cur:
            sql = (
                "INSERT INTO nf_model_runs ("
                " table_name, loto, unique_ids, model_name, backend, horizon,"
                " loss, metric, optimization_config, search_space, status,"
                " resource_summary, system_info"
                " ) VALUES ("
                " %(table_name)s, %(loto)s, %(unique_ids)s, %(model_name)s,"
                " %(backend)s, %(horizon)s, %(loss)s, %(metric)s,"
                " %(optimization_config)s::jsonb, %(search_space)s::jsonb,"
                " 'running', %(resource_summary)s::jsonb,"
                " %(system_info)s::jsonb"
                " ) RETURNING id"
            )
            cur.execute(
                sql,
                {
                    "table_name": table_name,
                    "loto": loto,
                    "unique_ids": unique_ids_list,
                    "model_name": model_name,
                    "backend": backend,
                    "horizon": horizon,
                    "loss": loss,
                    "metric": metric,
                    "optimization_config": json.dumps(optimization_config),
                    "search_space": json.dumps(search_space or {}),
                    "resource_summary": json.dumps({"before": resource_snapshot}),
                    "system_info": json.dumps(system_info),
                },
            )
            run_id = cur.fetchone()[0]
        conn.commit()
    return int(run_id)


def log_run_end(
    run_id: int,
    status: str,
    metrics: Optional[Dict[str, Any]] = None,
    best_params: Optional[Dict[str, Any]] = None,
    model_properties: Optional[Dict[str, Any]] = None,
    resource_after: Optional[Dict[str, Any]] = None,
    extra_logs: Optional[str] = None,
) -> None:
    """実行完了時に nf_model_runs を更新。"""
    metrics = metrics or {}
    best_params = best_params or {}
    model_properties = model_properties or {}
    resource_after = resource_after or {}

    with get_connection() as conn:
        with conn.cursor() as cur:
            sql = (
                "UPDATE nf_model_runs SET"
                " status = %(status)s,"
                " end_time = NOW(),"
                " duration_seconds = EXTRACT(EPOCH FROM (NOW() - start_time)),"
                " metrics = COALESCE(metrics, '{}'::jsonb) || %(metrics)s::jsonb,"
                " best_params = COALESCE(best_params, '{}'::jsonb) || %(best_params)s::jsonb,"
                " model_properties = COALESCE(model_properties, '{}'::jsonb) || %(model_properties)s::jsonb,"
                " resource_summary = COALESCE(resource_summary, '{}'::jsonb) || %(resource_after)s::jsonb,"
                " logs = COALESCE(logs, '') || %(logs)s"
                " WHERE id = %(run_id)s"
            )
            cur.execute(
                sql,
                {
                    "run_id": run_id,
                    "status": status,
                    "metrics": json.dumps(metrics),
                    "best_params": json.dumps(best_params),
                    "model_properties": json.dumps(model_properties),
                    "resource_after": json.dumps({"after": resource_after}),
                    "logs": extra_logs or "",
                },
            )
        conn.commit()


def log_run_error(run_id: int, exc: BaseException) -> None:
    """エラー発生時の更新。"""
    tb = traceback.format_exc()
    msg = f"{type(exc).__name__}: {exc}"

    with get_connection() as conn:
        with conn.cursor() as cur:
            sql = (
                "UPDATE nf_model_runs SET"
                " status = 'failed',"
                " end_time = NOW(),"
                " duration_seconds = EXTRACT(EPOCH FROM (NOW() - start_time)),"
                " error_message = %(error_message)s,"
                " traceback = %(traceback)s"
                " WHERE id = %(run_id)s"
            )
            cur.execute(
                sql,
                {
                    "run_id": run_id,
                    "error_message": msg,
                    "traceback": tb,
                },
            )
        conn.commit()

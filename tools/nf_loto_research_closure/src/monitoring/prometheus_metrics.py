"""Prometheus 連携用のメトリクス定義。

- Prometheus / Grafana から参照できるように HTTP でメトリクスを公開
- モデル実行の開始・終了・エラーを Counter / Histogram / Gauge で記録

prometheus_client がインストールされていない環境では、何もしないスタブとして振る舞う。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server

    _PROM_AVAILABLE = True
except Exception:  # pylint: disable=broad-except
    # 依存が入っていない場合でもアプリ全体が落ちないようにする
    _PROM_AVAILABLE = False
    Counter = Gauge = Histogram = object  # type: ignore[assignment]
    def start_http_server(*args, **kwargs):  # type: ignore[override]
        return None

logger = logging.getLogger(__name__)

_server_started = False
_server_lock = threading.Lock()

# メトリクス定義（prometheus_client 利用時のみ有効）
if _PROM_AVAILABLE:
    RUNS_STARTED = Counter(
        "nf_model_runs_started_total",
        "Number of model runs that have been started.",
        labelnames=["model_name", "backend"],
    )
    RUNS_COMPLETED = Counter(
        "nf_model_runs_completed_total",
        "Number of model runs that have finished.",
        labelnames=["model_name", "backend", "status"],
    )
    RUNS_ACTIVE = Gauge(
        "nf_model_runs_active",
        "Number of model runs currently in progress.",
    )
    RUN_DURATION = Histogram(
        "nf_model_run_duration_seconds",
        "Histogram of model run durations in seconds.",
        labelnames=["model_name", "backend"],
        buckets=(10, 30, 60, 120, 300, 600, 1800, 3600),
    )
    LAST_RUN_CPU = Gauge(
        "nf_model_run_last_cpu_percent",
        "CPU percent at the end of the last finished run.",
    )
    LAST_RUN_MEMORY = Gauge(
        "nf_model_run_last_memory_used_bytes",
        "Used memory (bytes) at the end of the last finished run.",
    )
    LAST_RUN_TIMESTAMP = Gauge(
        "nf_model_run_last_timestamp_seconds",
        "Unix timestamp of the last finished run.",
    )
else:
    RUNS_STARTED = RUNS_COMPLETED = RUNS_ACTIVE = RUN_DURATION = None  # type: ignore[assignment]
    LAST_RUN_CPU = LAST_RUN_MEMORY = LAST_RUN_TIMESTAMP = None  # type: ignore[assignment]


def init_metrics_server(port: int = 8000) -> None:
    """Prometheus 用の HTTP メトリクスサーバを起動する。

    すでに起動済みの場合は何もしない。
    """
    global _server_started
    if not _PROM_AVAILABLE:
        logger.info("prometheus_client がインストールされていないため、metrics サーバは起動しません。")
        return

    with _server_lock:
        if _server_started:
            return
        start_http_server(port)
        _server_started = True
        logger.info("Prometheus metrics server started on port %d", port)


def _extract_cpu_and_memory(resource_snapshot: Dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    """resource_monitor.collect_resource_snapshot の戻り値から CPU とメモリを抽出。"""
    if not resource_snapshot:
        return None, None

    cpu = None
    mem = None

    cpu_info = resource_snapshot.get("cpu") or {}
    mem_info = resource_snapshot.get("memory") or {}

    # psutil.percent は float
    if isinstance(cpu_info, dict):
        cpu = cpu_info.get("percent")

    # memory used bytes
    if isinstance(mem_info, dict):
        mem = mem_info.get("used")

    return cpu, mem


def observe_run_start(
    model_name: str,
    backend: str,
) -> None:
    """実験開始時のメトリクス更新。"""
    if not _PROM_AVAILABLE:
        return

    try:
        RUNS_STARTED.labels(model_name=model_name, backend=backend).inc()
        RUNS_ACTIVE.inc()
    except Exception:  # noqa: BLE001
        logger.exception("Prometheus observe_run_start でエラーが発生しました。")


def observe_run_end(
    model_name: str,
    backend: str,
    status: str,
    duration_seconds: Optional[float],
    resource_after: Optional[Dict[str, Any]] = None,
) -> None:
    """実験終了時のメトリクス更新。"""
    if not _PROM_AVAILABLE:
        return

    try:
        RUNS_COMPLETED.labels(model_name=model_name, backend=backend, status=status).inc()
        if duration_seconds is not None:
            RUN_DURATION.labels(model_name=model_name, backend=backend).observe(duration_seconds)

        # リソース情報があれば CPU / メモリを更新
        cpu, mem = _extract_cpu_and_memory(resource_after or {})
        if cpu is not None:
            LAST_RUN_CPU.set(cpu)
        if mem is not None:
            LAST_RUN_MEMORY.set(mem)
        LAST_RUN_TIMESTAMP.set(time.time())

        # active を減らす（status に関わらず）
        RUNS_ACTIVE.dec()
    except Exception:  # noqa: BLE001
        logger.exception("Prometheus observe_run_end でエラーが発生しました。")


def observe_run_error(
    model_name: str,
    backend: str,
) -> None:
    """エラー発生時のメトリクス更新。

    エラー自体は log_run_error で DB に記録されるので、
    ここでは runs_completed_total に status="failed" を積み増すのではなく、
    必要に応じてダッシュボード側で status 別に集計してください。
    （通常は observe_run_end から status="failed" で呼ばれる想定）
    """
    # 現状では特別な処理は行っていないが、拡張用のフックとして定義。
    if not _PROM_AVAILABLE:
        return
    # 何か専用の counter を増やしたければここに追加する。
    return

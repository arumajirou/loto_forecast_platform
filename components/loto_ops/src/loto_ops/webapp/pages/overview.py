from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import text

from loto_ops.webapp.components import metric_row
from loto_ops.webapp.services.db_service import get_engine, get_status
from loto_ops.webapp.services.quality_service import quality_frames
from loto_ops.webapp.services.run_service import latest_runs

IMPORTANT_TABLES: list[tuple[str, str]] = [
    ("dataset", "loto_y_ts"),
    ("dataset", "loto_hist_feat"),
    ("dataset", "loto_y_ts_unified"),
    ("exog", "loto_y_ts_exog"),
    ("meta", "model_run"),
]


def _exact_table_count(schema: str, table: str) -> int | None:
    """PostgreSQLから正確な行数を取得する。

    Overviewは古い品質レポートや推定統計ではなく、現在のDB状態を直接表示する。
    """
    try:
        engine = get_engine()
        with engine.begin() as conn:
            exists = conn.execute(
                text(
                    """
                    SELECT EXISTS (
                      SELECT 1
                      FROM information_schema.tables
                      WHERE table_schema = :schema
                        AND table_name = :table
                    )
                    """
                ),
                {"schema": schema, "table": table},
            ).scalar()
            if not exists:
                return None
            return int(
                conn.execute(text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')).scalar() or 0
            )
    except Exception:
        return None


def _count_metrics() -> list[tuple[str, object, str | None]]:
    metrics: list[tuple[str, object, str | None]] = []
    for schema, table in IMPORTANT_TABLES:
        rows = _exact_table_count(schema, table)
        value: object = "missing" if rows is None else rows
        metrics.append((f"{schema}.{table}", value, "PostgreSQL exact COUNT(*)"))
    return metrics


def render() -> None:
    st.header("Overview")

    if st.button("🔄 キャッシュ更新", help="Streamlitのデータキャッシュをクリアして再取得します"):
        st.cache_data.clear()
        st.rerun()

    try:
        status = get_status()
        st.success(f"DB接続OK: {status['database']} / {status['user']} / {status['checked_at']}")
    except Exception as e:
        st.error(f"DB接続失敗: {e}")
        return

    metrics = _count_metrics()
    metric_row(metrics[:4])
    if len(metrics) > 4:
        metric_row(metrics[4:])

    try:
        profiles, issues = quality_frames()
    except Exception as e:
        st.warning(f"品質プロファイル取得に失敗しました: {e}")
        profiles = pd.DataFrame()
        issues = pd.DataFrame()

    if not issues.empty:
        st.warning("品質警告/エラーがあります")
        st.dataframe(issues, width="stretch")
    else:
        st.success("品質警告/エラーはありません")

    if not profiles.empty:
        with st.expander("テーブルプロファイル詳細", expanded=False):
            st.dataframe(profiles, width="stretch")

    runs = latest_runs(5)
    if runs:
        st.subheader("最近の実行")
        st.json(runs[0])

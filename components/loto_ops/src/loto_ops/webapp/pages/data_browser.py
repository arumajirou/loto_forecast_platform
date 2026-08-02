from __future__ import annotations

import streamlit as st

from loto_ops.webapp.services.table_service import (
    list_tables,
    preview_table,
    table_columns,
    table_count,
)


def render() -> None:
    st.header("Data Browser")
    tables = list_tables()
    if tables.empty:
        st.warning("テーブルが見つかりません")
        return
    labels = [f"{r.table_schema}.{r.table_name}" for r in tables.itertuples()]
    selected = st.selectbox("テーブル", labels)
    schema, table = selected.split(".", 1)
    limit = st.slider("表示件数", 10, 5000, 100)
    try:
        st.metric("行数", table_count(schema, table))
        st.subheader("カラム")
        st.dataframe(table_columns(schema, table), use_container_width=True)
        st.subheader("プレビュー")
        st.dataframe(preview_table(schema, table, limit), use_container_width=True)
    except Exception as e:
        st.error(str(e))

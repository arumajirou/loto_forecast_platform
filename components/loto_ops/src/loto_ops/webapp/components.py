from __future__ import annotations

import streamlit as st


def metric_row(metrics: list[tuple[str, object, str | None]]) -> None:
    cols = st.columns(len(metrics))
    for col, (label, value, help_text) in zip(cols, metrics, strict=False):
        col.metric(label, value, help=help_text)


def danger_box(title: str, body: str) -> bool:
    st.error(title)
    st.caption(body)
    return st.text_input("確認文字列 RESET を入力") == "RESET"

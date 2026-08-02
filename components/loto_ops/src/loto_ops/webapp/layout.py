from __future__ import annotations

import streamlit as st


def setup_page(title: str = "Loto Ops Console") -> None:
    st.set_page_config(page_title=title, layout="wide")


def status_badge(label: str, status: str) -> None:
    colors = {
        "success": "#DCFCE7",
        "warning": "#FEF9C3",
        "failed": "#FEE2E2",
        "missing": "#E5E7EB",
    }
    color = colors.get(status, "#E5E7EB")
    st.markdown(
        f"<span style='background:{color};padding:0.35rem 0.6rem;border-radius:0.75rem'>{label}</span>",
        unsafe_allow_html=True,
    )

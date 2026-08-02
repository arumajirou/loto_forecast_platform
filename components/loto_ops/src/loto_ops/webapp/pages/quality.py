from __future__ import annotations

import streamlit as st

from loto_ops.webapp.services.quality_service import quality_frames


def render() -> None:
    st.header("Quality & Meta Analysis")
    profiles, issues = quality_frames()
    st.subheader("Table Profiles")
    st.dataframe(profiles, use_container_width=True)
    st.subheader("Issues")
    if issues.empty:
        st.success("重大な問題は検出されていません")
    else:
        st.dataframe(issues, use_container_width=True)

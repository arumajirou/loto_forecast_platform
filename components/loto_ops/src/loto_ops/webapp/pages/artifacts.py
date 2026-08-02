from __future__ import annotations

import streamlit as st

from loto_ops.webapp.services.artifact_service import list_artifacts


def render() -> None:
    st.header("Artifacts / ZIP")
    st.code("uv run loto-ops package --mode light", language="bash")
    st.code("uv run loto-ops package --mode full", language="bash")
    files = list_artifacts()
    for p in files[:100]:
        st.write(f"{p} ({p.stat().st_size:,} bytes)")

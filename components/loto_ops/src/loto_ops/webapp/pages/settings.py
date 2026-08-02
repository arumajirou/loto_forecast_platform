from __future__ import annotations

import streamlit as st

from loto_ops.config import load_settings
from loto_ops.perf.resource_governor import ResourceGovernor
from loto_ops.pipeline.exog_runner import ExogRunner


def render() -> None:
    st.header("Settings / Diagnostics")
    settings = load_settings()
    st.subheader("設定")
    st.json(settings.raw)

    st.subheader("性能診断")
    mode = st.selectbox("診断モード", ["auto", "light", "full"], index=0)
    governor = ResourceGovernor(settings)
    st.json(governor.diagnostics(mode=mode))

    st.subheader("既知問題チェック")
    runner = ExogRunner(settings)
    if runner.needs_sqlalchemy_inspect_patch():
        st.warning("exog_pipeline.py に sqlalchemy_inspect import不足があります")
        st.code("uv run loto-ops fix-exog", language="bash")
    else:
        st.success("exog_pipeline.py の既知import問題は検出されません")

    st.subheader("推奨コマンド")
    st.code(
        """cd /mnt/e/env/ts/loto_ops
source ./activate_env.sh

loto-ops perf-status --mode auto
loto-ops run-all-fast --mode light --with-exog --with-analysis --package light
loto-ops build-unified-fast --mode light
""",
        language="bash",
    )

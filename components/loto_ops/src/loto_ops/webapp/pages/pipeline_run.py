from __future__ import annotations

import os
import re
import subprocess
import time
from collections import deque
from pathlib import Path

import streamlit as st

from loto_ops.config import load_settings
from loto_ops.perf.resource_governor import ResourceGovernor

PROGRESS_RE = re.compile(r"\[progress\].*?(\d+(?:\.\d+)?)%\s*\|\s*(.*)$")


def _project_env() -> tuple[Path, dict[str, str]]:
    settings = load_settings()
    plan = ResourceGovernor(settings).make_plan(mode=os.getenv("LOTO_OPS_MODE", "auto"))
    env = os.environ.copy()
    env.setdefault("LOTO_OPS_CONFIG", str(settings.paths.ops_project / "configs" / "loto_ops.yaml"))
    env.update(plan.env())
    env["PATH"] = f"{settings.paths.ops_project / '.venv' / 'bin'}:{env.get('PATH', '')}"
    env["PYTHONPATH"] = f"{settings.paths.ops_project / 'src'}:{env.get('PYTHONPATH', '')}"
    return settings.paths.ops_project, env


def _run_with_progress(cmd: list[str], *, title: str, timeout_sec: int | None = None) -> None:
    project, env = _project_env()
    st.markdown(f"### {title}")
    st.code(" ".join(cmd), language="bash")

    progress = st.progress(0, text="開始待ち")
    status_box = st.empty()
    log_box = st.empty()
    recent_lines: deque[str] = deque(maxlen=180)

    started = time.perf_counter()
    proc = subprocess.Popen(
        cmd,
        cwd=project,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )

    last_percent = 0.0
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            recent_lines.append(line)
            match = PROGRESS_RE.search(line)
            if match:
                last_percent = max(last_percent, min(100.0, float(match.group(1))))
                progress.progress(int(last_percent), text=match.group(2)[:180])
            elif ">>>" in line:
                status_box.info(line)
            elif "<<<" in line:
                status_box.success(line)
            elif "!!!" in line or "Traceback" in line or "ERROR" in line:
                status_box.error(line)

            elapsed = time.perf_counter() - started
            log_box.code("\n".join(recent_lines), language="bash")
            if timeout_sec is not None and elapsed > timeout_sec:
                proc.terminate()
                raise TimeoutError(f"timeout: {timeout_sec}s")
    finally:
        rc = proc.wait()

    elapsed = time.perf_counter() - started
    if rc == 0:
        progress.progress(100, text=f"完了: {elapsed:.1f}秒")
        st.success(f"成功: returncode=0 / {elapsed:.1f}秒")
    else:
        st.error(f"失敗: returncode={rc} / {elapsed:.1f}秒")


def render() -> None:
    st.header("Pipeline Run")
    st.caption("light/full/autoを切り替え、PostgreSQL CTAS型の高速unified作成を優先します。")

    settings = load_settings()
    governor = ResourceGovernor(settings)

    with st.expander("現在の推奨リソース計画", expanded=True):
        mode_for_plan = st.selectbox("実行モード", ["light", "auto", "full"], index=0)
        plan = governor.make_plan(mode=mode_for_plan)
        st.json(plan.to_dict())
        st.code("\n".join(f"export {k}={v}" for k, v in plan.env().items()), language="bash")

    st.subheader("推奨実行")
    st.info(
        "日次運用は light を推奨します。full は研究用で、1000列級の横持ち結合になる場合があります。"
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("高速 light パイプライン", type="primary"):
            _run_with_progress(
                [
                    "loto-ops",
                    "run-all-fast",
                    "--mode",
                    "light",
                    "--engine",
                    "auto",
                    "--with-exog",
                    "--with-analysis",
                    "--package",
                    "light",
                ],
                title="run-all-fast light",
            )
    with col2:
        if st.button("研究用 full unified"):
            _run_with_progress(
                [
                    "loto-ops",
                    "build-unified-fast",
                    "--mode",
                    "full",
                    "--max-exog-cols",
                    "256",
                ],
                title="build-unified-fast full capped",
            )

    st.subheader("性能・DB制御")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("重いexogを退避してlight化"):
            _run_with_progress(["loto-ops", "exog-mode", "light"], title="exog-mode light")
    with c2:
        if st.button("重いexogを戻す"):
            _run_with_progress(["loto-ops", "exog-mode", "full"], title="exog-mode full")
    with c3:
        if st.button("性能診断"):
            _run_with_progress(["loto-ops", "perf-status"], title="perf-status")

    st.subheader("個別実行")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("1. データセット生成"):
            _run_with_progress(
                ["loto-ops", "build-dataset-fast", "--engine", "auto"], title="build-dataset-fast"
            )
    with col2:
        if st.button("2. PostgreSQL投入"):
            _run_with_progress(
                ["loto-ops", "load-postgres-fast", "--jobs", str(plan.copy_jobs)],
                title="load-postgres-fast",
            )
    with col3:
        if st.button("3. exog生成"):
            _run_with_progress(
                ["loto-ops", "build-exog", "--parallel-workers", str(plan.exog_workers)],
                title="build-exog",
            )

    col4, col5, col6 = st.columns(3)
    with col4:
        if st.button("4. unified高速作成"):
            _run_with_progress(
                ["loto-ops", "build-unified-fast", "--mode", mode_for_plan],
                title="build-unified-fast",
            )
    with col5:
        if st.button("5. 品質分析"):
            _run_with_progress(["loto-ops", "analyze"], title="analyze")
    with col6:
        if st.button("6. light ZIP作成"):
            _run_with_progress(["loto-ops", "package", "--mode", "light"], title="package light")

    with st.expander("CLIコマンド"):
        st.code(
            """cd /mnt/e/env/ts/loto_ops
source ./activate_env.sh

# 日次・通常運用
loto-ops run-all-fast --mode light --engine auto --with-exog --with-analysis --package light

# unifiedだけ高速再作成
loto-ops build-unified-fast --mode light

# 性能診断と推奨env
loto-ops perf-status --mode auto
loto-ops perf-status --mode auto --shell

# 重いexogの退避/復元
loto-ops exog-mode light
loto-ops exog-mode full
""",
            language="bash",
        )

    with st.expander("Danger Zone"):
        st.code("uv run loto-ops reset-tables --confirm-reset", language="bash")

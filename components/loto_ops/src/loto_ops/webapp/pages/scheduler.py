from __future__ import annotations

import json
import os
import re
import subprocess
from collections import deque

import streamlit as st

from loto_ops.config import load_settings

PROGRESS_RE = re.compile(r"\[progress\].*?(\d+(?:\.\d+)?)%\s*\|\s*(.*)$")


def _show_progress_file() -> None:
    settings = load_settings()
    progress_path = settings.paths.ops_project / "logs" / "scheduler" / "progress.json"
    if not progress_path.exists():
        st.info("まだ progress.json はありません。手動実行またはcron実行後に表示されます。")
        return
    try:
        data = json.loads(progress_path.read_text(encoding="utf-8"))
    except Exception as e:
        st.warning(f"progress.jsonを読めません: {e}")
        return
    percent = int(float(data.get("percent", 0)))
    st.progress(percent, text=f"{data.get('current_step')} / {data.get('message')} / {percent}%")
    st.json(data, expanded=False)


def _run_cmd(cmd: list[str], *, live_progress: bool = False) -> None:
    settings = load_settings()
    env = os.environ.copy()
    env.setdefault("LOTO_OPS_CONFIG", str(settings.paths.ops_project / "configs" / "loto_ops.yaml"))
    env["PATH"] = f"{settings.paths.ops_project / '.venv' / 'bin'}:{env.get('PATH', '')}"
    env["PYTHONPATH"] = f"{settings.paths.ops_project / 'src'}:{env.get('PYTHONPATH', '')}"

    if not live_progress:
        proc = subprocess.run(
            cmd,
            cwd=settings.paths.ops_project,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        st.code(proc.stdout or "", language="bash")
        if proc.returncode == 0:
            st.success(f"成功: {' '.join(cmd)}")
        else:
            st.error(f"失敗: returncode={proc.returncode}")
        return

    progress = st.progress(0, text="開始待ち")
    log_box = st.empty()
    recent_lines: deque[str] = deque(maxlen=180)
    proc = subprocess.Popen(
        cmd,
        cwd=settings.paths.ops_project,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        recent_lines.append(line)
        match = PROGRESS_RE.search(line)
        if match:
            progress.progress(int(float(match.group(1))), text=match.group(2)[:180])
        log_box.code("\n".join(recent_lines), language="bash")
    rc = proc.wait()
    if rc == 0:
        progress.progress(100, text="完了")
        st.success(f"成功: {' '.join(cmd)}")
    else:
        st.error(f"失敗: returncode={rc}")


def render() -> None:
    st.header("Scheduler")
    st.caption(
        "PCログイン時のUI/パイプライン起動と、月〜金06:30の定期実行を設定、確認、手動実行します。"
    )

    st.subheader("進捗")
    _show_progress_file()

    st.subheader("現在の状態確認")
    if st.button("スケジュール状態を確認", type="primary"):
        _run_cmd(["loto-ops", "schedule-status"])

    st.subheader("インストール")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Cron**")
        st.caption("互換用cron登録です。推奨はsystemd user timer（月〜金06:30）です。")
        if st.button("cronへ登録"):
            _run_cmd(["loto-ops", "schedule-install-cron"])
    with col2:
        st.markdown("**Kubuntu起動時**")
        st.caption("Streamlit UI、起動時パイプライン、平日timer、ブラウザ自動表示を登録します。")
        if st.button("Kubuntu自動運用を登録"):
            _run_cmd(["loto-ops", "schedule-install-kubuntu-startup"])
    with col3:
        st.markdown("**WSL起動時**")
        st.caption(
            "cron @reboot と WSL boot helper を作成します。/etc/wsl.conf変更はCLIで任意実行です。"
        )
        if st.button("WSL起動時登録"):
            _run_cmd(["loto-ops", "schedule-install-wsl-startup"])

    st.subheader("手動実行")
    reason = st.text_input("実行理由", value="manual_webapp")
    if st.button("今すぐ scheduled pipeline を実行"):
        _run_cmd(["loto-ops", "schedule-run-now", "--reason", reason], live_progress=True)

    st.subheader("CLIコマンド")
    st.code(
        """# 状態確認
loto-ops schedule-status

# 今すぐ実行(logs/scheduler/progress.json とログに進捗が出ます)
loto-ops schedule-run-now --reason manual

# 進捗JSONを確認
cat logs/scheduler/progress.json
""",
        language="bash",
    )

    st.subheader("作成・確認される主なファイル")
    st.code(
        """scripts/run_scheduled_pipeline.sh
scripts/install_user_services.sh
scripts/configure_runtime.sh
scripts/update_progress.py
logs/scheduler/progress.json
logs/scheduler/last_run.json
logs/scheduler/*.log
~/.config/systemd/user/loto-ops-startup.service
~/.config/autostart/loto-ops-startup.desktop
user crontab: # >>> loto-ops schedule >>> ...
""",
        language="text",
    )

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from loto_ops.config import load_settings
from loto_ops.scheduler.systemd_user import SystemdUserScheduler

ROOT = Path(__file__).resolve().parents[2]


def test_production_files_do_not_reference_retired_roots() -> None:
    retired = (
        "/mnt/e/env/fc/loto_ops_pipeline",
        "/mnt/e/env/ts/loto_ops_pipeline-fixed-20260729-v2",
        "/mnt/e/env/ts/loto_ops_pipeline",
    )
    targets = [
        ROOT / "src",
        ROOT / "scripts",
        ROOT / "configs",
        ROOT / "run_loto_ops.sh",
        ROOT / "setup_linux.sh",
        ROOT / "install_automation.sh",
    ]
    hits: list[str] = []
    for target in targets:
        paths = [target] if target.is_file() else [p for p in target.rglob("*") if p.is_file()]
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for value in retired:
                if value in text:
                    hits.append(f"{path.relative_to(ROOT)}: {value}")
    assert hits == []


def test_systemd_scheduler_is_weekday_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = load_settings(ROOT / "configs" / "loto_ops.yaml")
    result = SystemdUserScheduler(settings).install("06:30")
    timer = Path(result["timer"]).read_text(encoding="utf-8")
    service = Path(result["service"]).read_text(encoding="utf-8")
    assert "OnCalendar=Mon..Fri *-*-* 06:30:00" in timer
    assert "Persistent=true" in timer
    assert "run_scheduled_pipeline.sh weekday_daily" in service


def test_service_installer_renders_ui_startup_and_timer(tmp_path: Path) -> None:
    unit_dir = tmp_path / "units"
    autostart_dir = tmp_path / "autostart"
    runtime_env = tmp_path / "runtime.env"
    runtime_env.write_text('DB_PASSWORD="test"\n', encoding="utf-8")
    runtime_env.chmod(0o600)
    env = os.environ.copy()
    env.update(
        {
            "LOTO_OPS_UNIT_DIR": str(unit_dir),
            "LOTO_OPS_AUTOSTART_DIR": str(autostart_dir),
            "LOTO_OPS_RUNTIME_ENV": str(runtime_env),
            "LOTO_OPS_NO_SYSTEMCTL": "1",
            "LOTO_OPS_ALLOW_SYSTEM_PYTHON": "1",
        }
    )
    subprocess.run(
        ["bash", str(ROOT / "scripts" / "install_user_services.sh"), "06:30", "8520"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    ui = (unit_dir / "loto-ops-ui.service").read_text(encoding="utf-8")
    startup = (unit_dir / "loto-ops-startup.service").read_text(encoding="utf-8")
    timer = (unit_dir / "loto-ops-weekday.timer").read_text(encoding="utf-8")
    desktop = (autostart_dir / "loto-ops-open-ui.desktop").read_text(encoding="utf-8")
    assert "streamlit run" in ui
    assert "--server.port 8520" in ui
    assert "run_scheduled_pipeline.sh pc_startup" in startup
    assert "OnCalendar=Mon..Fri *-*-* 06:30:00" in timer
    assert "http://127.0.0.1:8520" in desktop


def test_scheduled_runner_has_no_plaintext_database_default() -> None:
    text = (ROOT / "scripts" / "run_scheduled_pipeline.sh").read_text(encoding="utf-8")
    assert 'DB_PASSWORD="${DB_PASSWORD:-z}"' not in text
    assert "configure_runtime.sh" in text
    assert "last_success_date" in text
    assert "notify-run-summary" in text

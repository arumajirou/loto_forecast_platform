from __future__ import annotations

from pathlib import Path

from loto_ops.config import AppSettings


class SystemdUserScheduler:
    """Create a weekday systemd user timer for the local pipeline."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.unit_name = settings.scheduler.get("systemd_unit_name", "loto-ops-weekday")
        self.unit_dir = Path.home() / ".config" / "systemd" / "user"

    def install(self, time_str: str = "06:30") -> dict[str, str]:
        hour, minute = time_str.split(":", 1)
        int(hour)
        int(minute)
        self.unit_dir.mkdir(parents=True, exist_ok=True)
        service = self.unit_dir / f"{self.unit_name}.service"
        timer = self.unit_dir / f"{self.unit_name}.timer"
        root = self.settings.paths.ops_project
        runtime_env = Path.home() / ".config" / "loto-ops" / "runtime.env"
        service.write_text(
            f"""[Unit]
Description=Loto Ops weekday pipeline
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=-{runtime_env}
WorkingDirectory={root}
ExecStart={root}/scripts/run_scheduled_pipeline.sh weekday_daily
""",
            encoding="utf-8",
        )
        timer.write_text(
            f"""[Unit]
Description=Run Loto Ops once on weekdays

[Timer]
OnCalendar=Mon..Fri *-*-* {hour}:{minute}:00
Persistent=true
AccuracySec=1min

[Install]
WantedBy=timers.target
""",
            encoding="utf-8",
        )
        return {"service": str(service), "timer": str(timer), "unit_name": self.unit_name}

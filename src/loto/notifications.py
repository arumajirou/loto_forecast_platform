"""Best-effort run notifications with secret-free defaults."""

from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
import urllib.request
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from loto.data.lineage import atomic_write_json, utc_now_iso


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class NotifyResult:
    channel: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class NotificationConfig:
    enabled: bool = False
    file_enabled: bool = True
    file_path: str = "notifications/events.jsonl"
    webhook_enabled: bool = False
    webhook_url: str = ""
    email_enabled: bool = False
    email_to: tuple[str, ...] = ()
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True

    @classmethod
    def from_env(cls) -> NotificationConfig:
        recipients = tuple(
            value.strip()
            for value in re.split(r"[,;]", os.getenv("LOTO_NOTIFY_EMAIL_TO", ""))
            if value.strip()
        )
        return cls(
            enabled=_env_bool("LOTO_NOTIFY_ENABLED", False),
            file_enabled=_env_bool("LOTO_NOTIFY_FILE_ENABLED", True),
            file_path=os.getenv("LOTO_NOTIFY_FILE_PATH", "notifications/events.jsonl"),
            webhook_enabled=_env_bool("LOTO_NOTIFY_WEBHOOK_ENABLED", False),
            webhook_url=os.getenv(
                "LOTO_NOTIFY_WEBHOOK_URL", os.getenv("LOTO_NOTIFY_SLACK_WEBHOOK_URL", "")
            ),
            email_enabled=_env_bool("LOTO_NOTIFY_EMAIL_ENABLED", False),
            email_to=recipients,
            smtp_host=os.getenv("LOTO_NOTIFY_SMTP_HOST", ""),
            smtp_port=int(os.getenv("LOTO_NOTIFY_SMTP_PORT", "587")),
            smtp_user=os.getenv("LOTO_NOTIFY_SMTP_USER", ""),
            smtp_password=os.getenv("LOTO_NOTIFY_SMTP_PASSWORD", ""),
            smtp_from=os.getenv("LOTO_NOTIFY_EMAIL_FROM", os.getenv("LOTO_NOTIFY_SMTP_USER", "")),
            smtp_starttls=_env_bool("LOTO_NOTIFY_SMTP_STARTTLS", True),
        )

    def redacted(self) -> dict[str, Any]:
        value = asdict(self)
        value["smtp_password"] = "***" if self.smtp_password else ""
        if value["webhook_url"]:
            value["webhook_url"] = value["webhook_url"].split("?", 1)[0][:40] + "..."
        return value


def build_run_summary(
    report: dict[str, Any], *, output_dir: str | Path | None = None
) -> dict[str, Any]:
    failures = report.get("failed_games") or report.get("failed_trials") or []
    status = str(report.get("status") or ("FAILED" if failures else "SUCCEEDED"))
    summary = {
        "schema_version": "1.0.0",
        "timestamp": utc_now_iso(),
        "run_id": report.get("run_id"),
        "status": status,
        "game": report.get("game"),
        "successful_games": report.get("successful_games"),
        "failed_games": report.get("failed_games"),
        "successful_trials": report.get("successful_trials"),
        "failed_trials": report.get("failed_trials"),
        "champion": report.get("champion"),
        "artifacts": [],
    }
    root = Path(output_dir) if output_dir else None
    if root and root.exists():
        for name in (
            "acquisition_report.json",
            "multi_game_summary.json",
            "research_summary.json",
            "model_leaderboard.csv",
            "events.jsonl",
        ):
            path = root / name
            if path.exists():
                summary["artifacts"].append(str(path))
    return summary


def format_summary_text(summary: dict[str, Any]) -> str:
    lines = [
        "Loto Forecast Platform run summary",
        f"status: {summary.get('status')}",
        f"run_id: {summary.get('run_id')}",
        f"game: {summary.get('game')}",
    ]
    if summary.get("successful_games") is not None:
        lines.append(f"successful_games: {summary.get('successful_games')}")
    if summary.get("failed_games"):
        lines.append(f"failed_games: {summary.get('failed_games')}")
    if summary.get("champion"):
        champion = summary["champion"]
        lines.append(f"champion: {champion.get('model_id', champion)}")
    if summary.get("artifacts"):
        lines.append("artifacts:")
        lines.extend(f"- {path}" for path in summary["artifacts"])
    return "\n".join(lines)


class NotificationSender:
    def __init__(
        self, config: NotificationConfig | None = None, *, base_dir: str | Path = "."
    ) -> None:
        self.config = config or NotificationConfig.from_env()
        self.base_dir = Path(base_dir)

    def send_file(self, summary: dict[str, Any]) -> NotifyResult:
        if not self.config.file_enabled:
            return NotifyResult("file", "SKIPPED", "disabled")
        path = Path(self.config.file_path)
        if not path.is_absolute():
            path = self.base_dir / path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(summary, ensure_ascii=False, default=str) + "\n")
        return NotifyResult("file", "SENT", str(path))

    def send_webhook(self, summary: dict[str, Any]) -> NotifyResult:
        if not self.config.webhook_enabled:
            return NotifyResult("webhook", "SKIPPED", "disabled")
        if not self.config.webhook_url:
            return NotifyResult("webhook", "SKIPPED", "missing_url")
        payload = json.dumps(
            {"text": format_summary_text(summary), "summary": summary}, ensure_ascii=False
        ).encode()
        request = urllib.request.Request(
            self.config.webhook_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "loto-forecast-platform/2.1",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - explicit configured endpoint
            status = int(getattr(response, "status", 200))
        if status >= 300:
            raise RuntimeError(f"webhook status={status}")
        return NotifyResult("webhook", "SENT", f"status={status}")

    def send_email(self, summary: dict[str, Any]) -> NotifyResult:
        if not self.config.email_enabled:
            return NotifyResult("email", "SKIPPED", "disabled")
        missing = [
            name
            for name, value in {
                "email_to": self.config.email_to,
                "smtp_host": self.config.smtp_host,
                "smtp_from": self.config.smtp_from,
            }.items()
            if not value
        ]
        if missing:
            return NotifyResult("email", "SKIPPED", "missing:" + ",".join(missing))
        message = EmailMessage()
        message["Subject"] = f"[Loto] {summary.get('status')} {summary.get('run_id') or ''}".strip()
        message["From"] = self.config.smtp_from
        message["To"] = ", ".join(self.config.email_to)
        message.set_content(format_summary_text(summary))
        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=20) as client:
            if self.config.smtp_starttls:
                client.starttls(context=ssl.create_default_context())
            if self.config.smtp_user:
                client.login(self.config.smtp_user, self.config.smtp_password)
            client.send_message(message)
        return NotifyResult("email", "SENT", f"recipients={len(self.config.email_to)}")

    def send_all(
        self, summary: dict[str, Any], *, fail_on_error: bool = False
    ) -> list[NotifyResult]:
        if not self.config.enabled:
            # File audit remains useful and contains no external side effect.
            return [self.send_file(summary), NotifyResult("external", "SKIPPED", "global_disabled")]
        results: list[NotifyResult] = [self.send_file(summary)]
        for send in (self.send_webhook, self.send_email):
            try:
                results.append(send(summary))
            except Exception as exc:  # best effort by default
                result = NotifyResult(
                    send.__name__.removeprefix("send_"), "FAILED", f"{type(exc).__name__}: {exc}"
                )
                results.append(result)
                if fail_on_error:
                    raise
        return results


def write_notification_report(results: list[NotifyResult], path: str | Path) -> Path:
    return atomic_write_json(
        path, {"timestamp": utc_now_iso(), "results": [item.to_dict() for item in results]}
    )

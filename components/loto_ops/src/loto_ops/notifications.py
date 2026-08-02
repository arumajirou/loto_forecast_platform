from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from sqlalchemy import text

from loto_ops.config import AppSettings
from loto_ops.db.connection import make_engine

IMPORTANT_TABLES = [
    ("dataset", "loto_y_ts"),
    ("dataset", "loto_hist_feat"),
    ("exog", "loto_y_ts_exog"),
    ("dataset", "loto_y_ts_unified"),
]


@dataclass(frozen=True)
class NotifyResult:
    channel: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"channel": self.channel, "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class NotificationConfig:
    email_enabled: bool
    email_to: list[str]
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_starttls: bool
    slack_enabled: bool
    slack_webhook_url: str

    @classmethod
    def from_env(cls) -> NotificationConfig:
        email_to_raw = os.getenv("LOTO_NOTIFY_EMAIL_TO", "")
        email_to = [v.strip() for v in re.split(r"[,;]", email_to_raw) if v.strip()]
        smtp_user = os.getenv("LOTO_NOTIFY_SMTP_USER", os.getenv("SMTP_USER", ""))
        smtp_password = os.getenv("LOTO_NOTIFY_SMTP_PASSWORD", os.getenv("SMTP_PASSWORD", ""))
        smtp_host = os.getenv("LOTO_NOTIFY_SMTP_HOST", os.getenv("SMTP_HOST", ""))
        smtp_port = int(os.getenv("LOTO_NOTIFY_SMTP_PORT", os.getenv("SMTP_PORT", "587")))
        smtp_from = os.getenv("LOTO_NOTIFY_EMAIL_FROM", os.getenv("SMTP_FROM", smtp_user))
        email_enabled = os.getenv("LOTO_NOTIFY_EMAIL_ENABLED", "1") not in {
            "0",
            "false",
            "False",
            "no",
            "NO",
        }
        slack_url = os.getenv("LOTO_NOTIFY_SLACK_WEBHOOK_URL", os.getenv("SLACK_WEBHOOK_URL", ""))
        slack_enabled = os.getenv("LOTO_NOTIFY_SLACK_ENABLED", "1") not in {
            "0",
            "false",
            "False",
            "no",
            "NO",
        }
        starttls = os.getenv("LOTO_NOTIFY_SMTP_STARTTLS", "1") not in {
            "0",
            "false",
            "False",
            "no",
            "NO",
        }
        return cls(
            email_enabled=email_enabled,
            email_to=email_to,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_password=smtp_password,
            smtp_from=smtp_from,
            smtp_starttls=starttls,
            slack_enabled=slack_enabled,
            slack_webhook_url=slack_url,
        )


def _read_json(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": f"{type(exc).__name__}: {exc}", "_path": str(path)}


def _latest_scheduler_file(log_dir: Path, name: str) -> Path | None:
    candidates = sorted(
        log_dir.glob(name), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True
    )
    return candidates[0] if candidates else None


def _extract_zip_paths(log_file: Path | None) -> list[str]:
    if not log_file or not log_file.exists():
        return []
    text_body = log_file.read_text(encoding="utf-8", errors="replace")
    paths = re.findall(r'"zip_path"\s*:\s*"([^"]+)"', text_body)
    return list(dict.fromkeys(paths))


def _tail_log(log_file: Path | None, max_lines: int = 40) -> str:
    if not log_file or not log_file.exists():
        return ""
    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


class RunSummaryBuilder:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def table_counts(self) -> list[dict[str, Any]]:
        engine = make_engine(self.settings.db)
        rows: list[dict[str, Any]] = []
        try:
            with engine.begin() as conn:
                for schema, table in IMPORTANT_TABLES:
                    full_name = f"{schema}.{table}"
                    exists = conn.execute(
                        text(
                            """
                            SELECT EXISTS (
                              SELECT 1
                              FROM information_schema.tables
                              WHERE table_schema = :schema
                                AND table_name = :table
                            )
                            """
                        ),
                        {"schema": schema, "table": table},
                    ).scalar()
                    if exists:
                        count = conn.execute(
                            text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
                        ).scalar()
                    else:
                        count = None
                    rows.append({"table": full_name, "rows": count, "exists": bool(exists)})
        except Exception as exc:
            rows.append(
                {
                    "table": "database",
                    "rows": None,
                    "exists": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        finally:
            engine.dispose()
        return rows

    def build(
        self,
        *,
        status: str | None = None,
        reason: str | None = None,
        log_file: Path | None = None,
        progress_file: Path | None = None,
        last_run_file: Path | None = None,
        include_log_tail: bool = True,
    ) -> dict[str, Any]:
        scheduler_dir = self.settings.paths.ops_project / "logs" / "scheduler"
        last_run_file = last_run_file or scheduler_dir / "last_run.json"
        progress_file = progress_file or scheduler_dir / "progress.json"
        last_run = _read_json(last_run_file)
        progress = _read_json(progress_file)

        raw_log_file = log_file or Path(str(last_run.get("log_file", "")))
        if not raw_log_file or str(raw_log_file) == ".":
            raw_log_file = _latest_scheduler_file(scheduler_dir, "*.log")

        summary = {
            "status": status or str(last_run.get("status") or progress.get("status") or "unknown"),
            "reason": reason or str(last_run.get("reason") or progress.get("reason") or "unknown"),
            "started_at": last_run.get("started_at") or progress.get("started_at"),
            "finished_at": last_run.get("finished_at") or progress.get("updated_at"),
            "percent": progress.get("percent"),
            "current_step": progress.get("current_step"),
            "message": progress.get("message"),
            "log_file": str(raw_log_file) if raw_log_file else "",
            "progress_file": str(progress_file),
            "last_run_file": str(last_run_file),
            "zip_paths": _extract_zip_paths(raw_log_file),
            "table_counts": self.table_counts(),
            "steps": progress.get("steps", []),
        }
        if include_log_tail:
            summary["log_tail"] = _tail_log(raw_log_file)
        return summary


def format_summary_text(summary: dict[str, Any]) -> str:
    status = summary.get("status", "unknown")
    reason = summary.get("reason", "unknown")
    lines = [
        "Loto Ops 実行結果サマリー",
        "",
        f"状態: {status}",
        f"理由/実行種別: {reason}",
        f"開始: {summary.get('started_at')}",
        f"終了: {summary.get('finished_at')}",
        f"進捗: {summary.get('percent')}% / {summary.get('current_step')}",
        f"メッセージ: {summary.get('message')}",
        "",
        "重要テーブル件数:",
    ]
    for row in summary.get("table_counts", []):
        rows = row.get("rows")
        rows_text = "missing" if rows is None else f"{rows:,}"
        lines.append(f"- {row.get('table')}: {rows_text}")

    zip_paths = summary.get("zip_paths") or []
    if zip_paths:
        lines.extend(["", "成果物ZIP:"])
        lines.extend(f"- {p}" for p in zip_paths)

    lines.extend(
        [
            "",
            f"ログ: {summary.get('log_file')}",
            f"進捗JSON: {summary.get('progress_file')}",
        ]
    )

    steps = summary.get("steps") or []
    if steps:
        lines.extend(["", "ステップ:"])
        for s in steps:
            lines.append(
                f"- {s.get('index')}. {s.get('name')}: {s.get('status')} "
                f"({s.get('started_at')} -> {s.get('finished_at')}) {s.get('message') or ''}".rstrip()
            )

    log_tail = summary.get("log_tail")
    if log_tail:
        lines.extend(["", "直近ログ:", log_tail])
    return "\n".join(lines)


def format_slack_text(summary: dict[str, Any]) -> str:
    status = str(summary.get("status", "unknown"))
    emoji = "✅" if status == "success" else "⚠️" if status == "warning" else "❌"
    counts = ", ".join(
        f"{row.get('table')}={row.get('rows')}" for row in summary.get("table_counts", [])
    )
    zip_paths = summary.get("zip_paths") or []
    zip_text = "\n".join(f"• `{p}`" for p in zip_paths) if zip_paths else "なし"
    return (
        f"{emoji} *Loto Ops 実行結果*: `{status}`\n"
        f"• reason: `{summary.get('reason')}`\n"
        f"• progress: `{summary.get('percent')}%` / `{summary.get('current_step')}`\n"
        f"• started: `{summary.get('started_at')}`\n"
        f"• finished: `{summary.get('finished_at')}`\n"
        f"• counts: `{counts}`\n"
        f"• zip:\n{zip_text}\n"
        f"• log: `{summary.get('log_file')}`"
    )


class NotificationSender:
    def __init__(self, config: NotificationConfig | None = None) -> None:
        self.config = config or NotificationConfig.from_env()

    def send_all(
        self, summary: dict[str, Any], *, fail_on_error: bool = False
    ) -> list[NotifyResult]:
        results: list[NotifyResult] = []
        for func in (self.send_email, self.send_slack):
            try:
                results.append(func(summary))
            except Exception as exc:
                result = NotifyResult(
                    func.__name__.removeprefix("send_"), "failed", f"{type(exc).__name__}: {exc}"
                )
                results.append(result)
                if fail_on_error:
                    raise
        return results

    def send_email(self, summary: dict[str, Any]) -> NotifyResult:
        cfg = self.config
        if not cfg.email_enabled:
            return NotifyResult("email", "skipped", "LOTO_NOTIFY_EMAIL_ENABLED=0")
        if not cfg.email_to:
            return NotifyResult("email", "skipped", "LOTO_NOTIFY_EMAIL_TO is empty")
        if not cfg.smtp_user or not cfg.smtp_password:
            return NotifyResult("email", "skipped", "SMTP credentials are missing")
        if not cfg.smtp_from:
            return NotifyResult("email", "skipped", "SMTP from address is missing")

        status = summary.get("status", "unknown")
        reason = summary.get("reason", "unknown")
        msg = EmailMessage()
        msg["Subject"] = f"[loto-ops] {status} - {reason}"
        msg["From"] = cfg.smtp_from
        msg["To"] = ", ".join(cfg.email_to)
        msg.set_content(format_summary_text(summary))

        context = ssl.create_default_context()
        if cfg.smtp_starttls:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(cfg.smtp_user, cfg.smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(
                cfg.smtp_host, cfg.smtp_port, context=context, timeout=30
            ) as server:
                server.login(cfg.smtp_user, cfg.smtp_password)
                server.send_message(msg)
        return NotifyResult("email", "sent", ",".join(cfg.email_to))

    def send_slack(self, summary: dict[str, Any]) -> NotifyResult:
        cfg = self.config
        if not cfg.slack_enabled:
            return NotifyResult("slack", "skipped", "LOTO_NOTIFY_SLACK_ENABLED=0")
        if not cfg.slack_webhook_url:
            return NotifyResult("slack", "skipped", "SLACK_WEBHOOK_URL is empty")
        payload = json.dumps({"text": format_slack_text(summary)}, ensure_ascii=False).encode(
            "utf-8"
        )
        req = urllib.request.Request(
            cfg.slack_webhook_url,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                body = res.read().decode("utf-8", errors="replace")
                return NotifyResult("slack", "sent", f"HTTP {res.status}: {body[:200]}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Slack webhook failed HTTP {exc.code}: {body[:500]}") from exc

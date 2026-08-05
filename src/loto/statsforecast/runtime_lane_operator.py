from __future__ import annotations

import hashlib
import json
import os
import shutil
import smtplib
import subprocess
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping


@dataclass(frozen=True)
class OperatorResult:
    run_id: str
    output_dir: Path
    report_path: Path
    notification_report_path: Path
    decision: str
    formal_pass: bool


@dataclass(frozen=True)
class EmailSettings:
    host: str
    port: int
    sender: str
    recipient: str
    username: str | None
    password: str | None
    starttls: bool
    use_ssl: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _write_json(path: Path, payload: Any) -> None:
    content = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    _atomic_write(path, content)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_sums(root: Path) -> Path:
    checksum_path = root / "SHA256SUMS"
    rows: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink() and path != checksum_path:
            relative = path.relative_to(root).as_posix()
            rows.append(f"{_sha256_file(path)}  {relative}")
    _atomic_write(checksum_path, ("\n".join(rows) + "\n").encode("utf-8"))
    return checksum_path


def _valid_commit(value: str) -> bool:
    normalized = value.lower()
    return len(normalized) == 40 and all(
        character in "0123456789abcdef" for character in normalized
    )


def _bool_env(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def email_settings_from_env(
    env: Mapping[str, str] | None = None,
) -> EmailSettings | None:
    values = os.environ if env is None else env
    host = values.get("LOTO_NOTIFY_SMTP_HOST", "").strip()
    sender = values.get("LOTO_NOTIFY_EMAIL_FROM", "").strip()
    recipient = values.get("LOTO_NOTIFY_EMAIL_TO", "").strip()
    if not host or not sender or not recipient:
        return None
    use_ssl = _bool_env(values.get("LOTO_NOTIFY_SMTP_SSL"))
    port_text = values.get("LOTO_NOTIFY_SMTP_PORT", "").strip()
    port = int(port_text) if port_text else (465 if use_ssl else 587)
    if not 1 <= port <= 65535:
        raise ValueError("LOTO_NOTIFY_SMTP_PORT must be between 1 and 65535")
    username = values.get("LOTO_NOTIFY_SMTP_USER") or None
    password = values.get("LOTO_NOTIFY_SMTP_PASSWORD") or None
    starttls = _bool_env(
        values.get("LOTO_NOTIFY_SMTP_STARTTLS"),
        default=not use_ssl,
    )
    if use_ssl and starttls:
        raise ValueError("SMTP SSL and STARTTLS cannot both be enabled")
    return EmailSettings(
        host=host,
        port=port,
        sender=sender,
        recipient=recipient,
        username=username,
        password=password,
        starttls=starttls,
        use_ssl=use_ssl,
    )


def _email_settings_summary(settings: EmailSettings | None) -> dict[str, Any]:
    if settings is None:
        return {
            "configured": False,
            "credential_present": False,
        }
    return {
        "configured": True,
        "host": settings.host,
        "port": settings.port,
        "sender": settings.sender,
        "recipient": settings.recipient,
        "username_present": settings.username is not None,
        "credential_present": settings.password is not None,
        "starttls": settings.starttls,
        "ssl": settings.use_ssl,
    }


def send_email_notification(
    subject: str,
    body: str,
    *,
    settings: EmailSettings | None,
    smtp_factory: Callable[..., Any] = smtplib.SMTP,
    smtp_ssl_factory: Callable[..., Any] = smtplib.SMTP_SSL,
) -> dict[str, Any]:
    summary = _email_settings_summary(settings)
    if settings is None:
        return {
            "channel": "email",
            "status": "SKIPPED",
            "reason": "SMTP environment is incomplete",
            "settings": summary,
        }
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.sender
    message["To"] = settings.recipient
    message.set_content(body)
    factory = smtp_ssl_factory if settings.use_ssl else smtp_factory
    try:
        with factory(settings.host, settings.port, timeout=30) as client:
            if settings.starttls:
                client.starttls()
            if settings.username is not None:
                client.login(settings.username, settings.password or "")
            client.send_message(message)
    except Exception as exc:
        return {
            "channel": "email",
            "status": "FAILED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "settings": summary,
        }
    return {
        "channel": "email",
        "status": "SENT",
        "settings": summary,
    }


def send_tts_notification(
    message: str,
    *,
    which_fn: Callable[[str], str | None] = shutil.which,
    run_fn: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    selected: tuple[str, list[str]] | None = None
    for executable, arguments in (
        ("spd-say", ["spd-say", "--wait", message]),
        ("espeak-ng", ["espeak-ng", message]),
        ("espeak", ["espeak", message]),
    ):
        resolved = which_fn(executable)
        if resolved:
            arguments[0] = resolved
            selected = executable, arguments
            break
    if selected is None:
        return {
            "channel": "tts",
            "status": "SKIPPED",
            "reason": "no supported TTS executable was found",
        }
    executable, command = selected
    try:
        completed = run_fn(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except Exception as exc:
        return {
            "channel": "tts",
            "status": "FAILED",
            "executable": executable,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    return {
        "channel": "tts",
        "status": "SENT" if completed.returncode == 0 else "FAILED",
        "executable": executable,
        "returncode": completed.returncode,
        "stderr": completed.stderr.strip(),
    }


def _safe_notification_call(
    channel: str,
    notifier: Callable[..., dict[str, Any]],
    *args: str,
) -> dict[str, Any]:
    try:
        result = notifier(*args)
    except Exception as exc:
        return {
            "channel": channel,
            "status": "FAILED",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    if not isinstance(result, dict):
        return {
            "channel": channel,
            "status": "FAILED",
            "error_type": "TypeError",
            "error": "notification result must be a dictionary",
        }
    return result


def _render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# StatsForecast Target-host Operator Report",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- Formal pass: `{str(bool(report.get('formal_pass'))).lower()}`",
        f"- Expected commit: `{report.get('expected_commit')}`",
        f"- End-to-End directory: `{report.get('end_to_end_dir')}`",
        f"- Triage directory: `{report.get('triage_dir')}`",
        "",
        "## Safety boundary",
        "",
        "- Automatic remediation: `false`",
        "- Git mutation: `false`",
        "- Holdout opened: `false`",
        "- Prospective actual known: `false`",
        "- Predictive accuracy certified: `false`",
        "",
        "## Failures",
        "",
    ]
    failures = report.get("failures")
    if isinstance(failures, list) and failures:
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def run_target_host_operator(
    repo_root: Path,
    output_root: Path,
    *,
    wheelhouse: Path | None = None,
    run_id: str | None = None,
    prepare_offline: bool = False,
    offline: bool = False,
    expected_commit: str,
    expected_seed: int = 1,
    horizon: int = 1,
    uv_executable: str = "uv",
    enable_tts: bool = False,
    enable_email: bool = False,
    environment: Mapping[str, str] | None = None,
    git_context_fn: Callable[[Path], dict[str, Any]] | None = None,
    end_to_end_runner: Callable[..., Any] | None = None,
    triage_runner: Callable[..., Any] | None = None,
    tts_notifier: Callable[[str], dict[str, Any]] | None = None,
    email_notifier: Callable[[str, str], dict[str, Any]] | None = None,
) -> OperatorResult:
    if prepare_offline and offline:
        raise ValueError("--prepare-offline and --offline are mutually exclusive")
    if (prepare_offline or offline) and wheelhouse is None:
        raise ValueError("wheelhouse is required for the selected execution mode")
    if not _valid_commit(expected_commit):
        raise ValueError("expected_commit must be a full 40-character SHA")
    if expected_seed < 0 or horizon < 1:
        raise ValueError("seed and horizon must be valid fixed values")

    run_id = run_id or datetime.now(timezone.utc).strftime(
        "statsforecast-operator-%Y%m%d-%H%M%S"
    )
    output_root.mkdir(parents=True, exist_ok=True)
    output_dir = output_root / run_id
    output_dir.mkdir(parents=False, exist_ok=False)
    report_path = output_dir / "OPERATOR_REPORT.json"
    notification_report_path = output_dir / "OPERATOR_NOTIFICATION_REPORT.json"

    if git_context_fn is None:
        from .runtime_lane_end_to_end import resolve_git_context

        git_context_fn = resolve_git_context
    git_context = git_context_fn(repo_root)
    normalized_commit = expected_commit.lower()
    failures: list[str] = []
    if git_context.get("head") != normalized_commit:
        failures.append(
            "Git HEAD mismatch: "
            f"expected {normalized_commit}, got {git_context.get('head')}"
        )
    if not git_context.get("working_tree_clean"):
        failures.append("working tree is not clean")

    _write_json(
        output_dir / "OPERATOR_PREFLIGHT.json",
        {
            "schema_version": 1,
            "captured_at_utc": _utc_now(),
            "expected_commit": normalized_commit,
            "git_context": git_context,
            "seed": expected_seed,
            "horizon": horizon,
            "prepare_offline": prepare_offline,
            "offline": offline,
            "wheelhouse": str(wheelhouse.resolve()) if wheelhouse else None,
            "status": "PASS" if not failures else "FAILED",
            "failures": failures,
        },
    )

    formal_pass = False
    decision = "MERGE_BLOCKED"
    end_to_end_dir: Path | None = None
    triage_dir: Path | None = None
    exception: dict[str, Any] | None = None

    if not failures:
        try:
            if end_to_end_runner is None:
                from .runtime_lane_end_to_end_hardening import (
                    run_end_to_end_certification,
                )

                end_to_end_runner = run_end_to_end_certification
            result = end_to_end_runner(
                repo_root,
                output_dir / "end-to-end",
                wheelhouse=wheelhouse,
                run_id="run",
                prepare_offline=prepare_offline,
                offline=offline,
                expected_commit=normalized_commit,
                expected_seed=expected_seed,
                horizon=horizon,
                uv_executable=uv_executable,
            )
            end_to_end_dir = Path(result.output_dir)
            formal_pass = bool(result.formal_pass)
            decision = str(result.decision)
            if not formal_pass:
                if triage_runner is None:
                    from .runtime_lane_triage import triage_end_to_end_run

                    triage_runner = triage_end_to_end_run
                triage_result = triage_runner(
                    end_to_end_dir,
                    output_dir / "triage",
                )
                triage_dir = Path(triage_result.output_dir)
                failures.append(
                    "End-to-End certification did not produce RUNTIME_CERTIFIED"
                )
        except Exception as exc:
            exception = {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
            failures.append(f"{type(exc).__name__}: {exc}")
            _write_json(output_dir / "OPERATOR_EXCEPTION.json", exception)

    status = "RUNTIME_CERTIFIED" if formal_pass else "MERGE_BLOCKED"
    report: MutableMapping[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "status": status,
        "decision": decision if formal_pass else "MERGE_BLOCKED",
        "formal_pass": formal_pass,
        "expected_commit": normalized_commit,
        "seed": expected_seed,
        "horizon": horizon,
        "end_to_end_dir": str(end_to_end_dir) if end_to_end_dir else None,
        "triage_dir": str(triage_dir) if triage_dir else None,
        "automatic_remediation_executed": False,
        "git_mutated": False,
        "holdout_opened": False,
        "prospective_actual_known": False,
        "predictive_accuracy_certified": False,
        "notification_failures_affect_decision": False,
        "failures": failures,
        "exception": exception,
        "finished_at_utc": _utc_now(),
    }
    _write_json(report_path, report)
    _atomic_write(
        output_dir / "OPERATOR_REPORT.md",
        _render_markdown(report).encode("utf-8"),
    )

    message = (
        "StatsForecast runtime certification succeeded."
        if formal_pass
        else "StatsForecast runtime certification is blocked. Review the evidence."
    )
    subject = (
        "[PASS] StatsForecast runtime certification"
        if formal_pass
        else "[BLOCKED] StatsForecast runtime certification"
    )
    notification_results: list[dict[str, Any]] = []
    if enable_tts:
        notifier = tts_notifier or send_tts_notification
        notification_results.append(
            _safe_notification_call("tts", notifier, message)
        )
    else:
        notification_results.append(
            {"channel": "tts", "status": "DISABLED"}
        )
    if enable_email:
        if email_notifier is None:

            def configured_email(subject_value: str, body_value: str) -> dict[str, Any]:
                settings = email_settings_from_env(environment)
                return send_email_notification(
                    subject_value,
                    body_value,
                    settings=settings,
                )

            email_notifier = configured_email
        notification_results.append(
            _safe_notification_call(
                "email",
                email_notifier,
                subject,
                _render_markdown(report),
            )
        )
    else:
        notification_results.append(
            {"channel": "email", "status": "DISABLED"}
        )
    _write_json(
        notification_report_path,
        {
            "schema_version": 1,
            "run_id": run_id,
            "results": notification_results,
            "affects_runtime_decision": False,
            "finished_at_utc": _utc_now(),
        },
    )
    _write_sums(output_dir)
    return OperatorResult(
        run_id=run_id,
        output_dir=output_dir,
        report_path=report_path,
        notification_report_path=notification_report_path,
        decision=report["decision"],
        formal_pass=formal_pass,
    )


__all__ = [
    "EmailSettings",
    "OperatorResult",
    "email_settings_from_env",
    "run_target_host_operator",
    "send_email_notification",
    "send_tts_notification",
]

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from loto.statsforecast.runtime_lane_operator import (
    email_settings_from_env,
    run_target_host_operator,
    send_email_notification,
    send_tts_notification,
)

COMMIT = "a" * 40


def clean_context(_repo: Path) -> dict:
    return {
        "head": COMMIT,
        "working_tree_clean": True,
        "status_porcelain": [],
    }


def fake_e2e(tmp_path: Path, *, passed: bool):
    output_dir = tmp_path / ("e2e-pass" if passed else "e2e-fail")
    output_dir.mkdir()
    return SimpleNamespace(
        output_dir=output_dir,
        formal_pass=passed,
        decision="RUNTIME_CERTIFIED" if passed else "MERGE_BLOCKED",
    )


def test_success_skips_triage_and_preserves_sha_evidence(tmp_path) -> None:
    triage_called = False

    def triage(*_args, **_kwargs):
        nonlocal triage_called
        triage_called = True

    result = run_target_host_operator(
        tmp_path,
        tmp_path / "out",
        run_id="success",
        expected_commit=COMMIT,
        git_context_fn=clean_context,
        end_to_end_runner=lambda *_args, **_kwargs: fake_e2e(
            tmp_path,
            passed=True,
        ),
        triage_runner=triage,
    )

    assert result.formal_pass is True
    assert result.decision == "RUNTIME_CERTIFIED"
    assert triage_called is False
    assert (result.output_dir / "SHA256SUMS").is_file()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["automatic_remediation_executed"] is False


def test_failure_runs_triage_but_not_remediation(tmp_path) -> None:
    triage_dir = tmp_path / "triage-result"

    def triage(*_args, **_kwargs):
        triage_dir.mkdir()
        return SimpleNamespace(output_dir=triage_dir)

    result = run_target_host_operator(
        tmp_path,
        tmp_path / "out",
        run_id="blocked",
        expected_commit=COMMIT,
        git_context_fn=clean_context,
        end_to_end_runner=lambda *_args, **_kwargs: fake_e2e(
            tmp_path,
            passed=False,
        ),
        triage_runner=triage,
    )

    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert result.formal_pass is False
    assert result.decision == "MERGE_BLOCKED"
    assert report["triage_dir"] == str(triage_dir)
    assert report["automatic_remediation_executed"] is False


def test_dirty_worktree_blocks_before_end_to_end(tmp_path) -> None:
    called = False

    def e2e(*_args, **_kwargs):
        nonlocal called
        called = True

    result = run_target_host_operator(
        tmp_path,
        tmp_path / "out",
        run_id="dirty",
        expected_commit=COMMIT,
        git_context_fn=lambda _repo: {
            "head": COMMIT,
            "working_tree_clean": False,
            "status_porcelain": [" M file.py"],
        },
        end_to_end_runner=e2e,
    )

    assert called is False
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert "working tree is not clean" in report["failures"]


def test_commit_mismatch_blocks_before_end_to_end(tmp_path) -> None:
    result = run_target_host_operator(
        tmp_path,
        tmp_path / "out",
        run_id="mismatch",
        expected_commit=COMMIT,
        git_context_fn=lambda _repo: {
            "head": "b" * 40,
            "working_tree_clean": True,
        },
        end_to_end_runner=lambda *_args, **_kwargs: pytest.fail(
            "must not execute"
        ),
    )

    assert result.formal_pass is False
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert any("Git HEAD mismatch" in item for item in report["failures"])


def test_notification_failure_does_not_change_runtime_pass(tmp_path) -> None:
    result = run_target_host_operator(
        tmp_path,
        tmp_path / "out",
        run_id="notify-failure",
        expected_commit=COMMIT,
        git_context_fn=clean_context,
        end_to_end_runner=lambda *_args, **_kwargs: fake_e2e(
            tmp_path,
            passed=True,
        ),
        enable_tts=True,
        enable_email=True,
        tts_notifier=lambda _message: {
            "channel": "tts",
            "status": "FAILED",
        },
        email_notifier=lambda _subject, _body: {
            "channel": "email",
            "status": "FAILED",
        },
    )

    assert result.formal_pass is True
    notification = json.loads(
        result.notification_report_path.read_text(encoding="utf-8")
    )
    assert notification["affects_runtime_decision"] is False


def test_tts_uses_fixed_argv_without_shell() -> None:
    captured = {}

    def run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "", "")

    report = send_tts_notification(
        "done; touch /tmp/unsafe",
        which_fn=lambda name: f"/usr/bin/{name}" if name == "spd-say" else None,
        run_fn=run,
    )

    assert report["status"] == "SENT"
    assert captured["command"] == [
        "/usr/bin/spd-say",
        "--wait",
        "done; touch /tmp/unsafe",
    ]
    assert "shell" not in captured["kwargs"]


def test_email_password_is_not_returned_in_report() -> None:
    env = {
        "LOTO_NOTIFY_SMTP_HOST": "smtp.example.test",
        "LOTO_NOTIFY_EMAIL_FROM": "from@example.test",
        "LOTO_NOTIFY_EMAIL_TO": "to@example.test",
        "LOTO_NOTIFY_SMTP_USER": "operator",
        "LOTO_NOTIFY_SMTP_PASSWORD": "super-secret",
    }
    settings = email_settings_from_env(env)
    sent = {}

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def starttls(self):
            sent["starttls"] = True

        def login(self, username, password):
            sent["login"] = (username, password)

        def send_message(self, _message):
            sent["message"] = True

    report = send_email_notification(
        "subject",
        "body",
        settings=settings,
        smtp_factory=FakeSMTP,
    )

    assert report["status"] == "SENT"
    assert sent["login"] == ("operator", "super-secret")
    assert "super-secret" not in json.dumps(report)


def test_missing_email_configuration_is_skipped() -> None:
    assert email_settings_from_env({}) is None
    report = send_email_notification(
        "subject",
        "body",
        settings=None,
    )
    assert report["status"] == "SKIPPED"


def test_notification_exception_is_evidence_only(tmp_path) -> None:
    def raise_notification(*_args):
        raise RuntimeError("notification transport failed")

    result = run_target_host_operator(
        tmp_path,
        tmp_path / "out",
        run_id="notify-exception",
        expected_commit=COMMIT,
        git_context_fn=clean_context,
        end_to_end_runner=lambda *_args, **_kwargs: fake_e2e(
            tmp_path,
            passed=True,
        ),
        enable_tts=True,
        enable_email=True,
        tts_notifier=raise_notification,
        email_notifier=raise_notification,
    )

    assert result.formal_pass is True
    notification = json.loads(
        result.notification_report_path.read_text(encoding="utf-8")
    )
    assert [row["status"] for row in notification["results"]] == [
        "FAILED",
        "FAILED",
    ]


def test_invalid_smtp_environment_is_evidence_only(tmp_path) -> None:
    result = run_target_host_operator(
        tmp_path,
        tmp_path / "out",
        run_id="invalid-smtp",
        expected_commit=COMMIT,
        git_context_fn=clean_context,
        end_to_end_runner=lambda *_args, **_kwargs: fake_e2e(
            tmp_path,
            passed=True,
        ),
        enable_email=True,
        environment={
            "LOTO_NOTIFY_SMTP_HOST": "smtp.example.test",
            "LOTO_NOTIFY_SMTP_PORT": "99999",
            "LOTO_NOTIFY_EMAIL_FROM": "from@example.test",
            "LOTO_NOTIFY_EMAIL_TO": "to@example.test",
        },
    )

    assert result.formal_pass is True
    notification = json.loads(
        result.notification_report_path.read_text(encoding="utf-8")
    )
    email = next(row for row in notification["results"] if row["channel"] == "email")
    assert email["status"] == "FAILED"
    assert email["error_type"] == "ValueError"


def test_invalid_execution_mode_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        run_target_host_operator(
            tmp_path,
            tmp_path / "out",
            expected_commit=COMMIT,
            wheelhouse=tmp_path / "wheels",
            prepare_offline=True,
            offline=True,
        )

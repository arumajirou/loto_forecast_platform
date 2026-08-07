from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from loto.github_audit.cli import main, parse_args
from loto.github_audit.core import EndpointRecord, GhClient, classify_error, redact
from loto.github_audit.reporting import finalize_report
from loto.github_audit.runner import AuditConfig, AuditRunner


def test_error_classification_is_explicit() -> None:
    assert classify_error("HTTP 403 Forbidden", 1) == "BLOCKED"
    assert classify_error("HTTP 404 Not Found", 1) == "NOT_AVAILABLE"
    assert classify_error("secondary rate limit", 1) == "RATE_LIMITED"
    assert classify_error("anything else", 1) == "FAILED"


def test_redaction_removes_nested_secret_values() -> None:
    assert redact({"token": "abc", "nested": {"password": "def"}, "name": "safe"}) == {
        "token": "<REDACTED>",
        "nested": {"password": "<REDACTED>"},
        "name": "safe",
    }


def test_self_test_emits_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--self-test"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "PASS",
        "test": "github_audit_self_test",
    }


def test_parser_defaults_to_repository() -> None:
    args = parse_args([])
    assert args.repo == "arumajirou/loto_forecast_platform"
    assert args.api_version == "2026-03-10"
    assert args.deep is False


def test_invalid_repository_form_is_rejected() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--repo", "missing-slash"])


def test_runner_rejects_invalid_repository_before_writing(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        AuditRunner(AuditConfig(repo="invalid", output_root=tmp_path))
    assert list(tmp_path.iterdir()) == []


def _base_client(run_dir: Path) -> GhClient:
    client = GhClient(repo="owner/repo", run_dir=run_dir)
    client.datasets.update(
        {
            "repository": {
                "visibility": "private",
                "private": True,
                "archived": False,
                "default_branch": "main",
                "allow_auto_merge": False,
                "allow_merge_commit": True,
                "allow_rebase_merge": True,
                "allow_squash_merge": True,
                "allow_update_branch": False,
            },
            "head_sha": "a" * 40,
            "main_combined_status": {"state": "success"},
            "main_check_runs": [],
            "issues": [],
            "pulls": [],
            "workflows": [],
            "workflow_runs": [],
            "branches": [],
            "action_job_rows": [],
            "dependabot_alerts_open": [],
            "code_scanning_alerts_open": [],
            "secret_scanning_alerts_open": [],
        }
    )
    return client


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        repo="owner/repo",
        api_version="2026-03-10",
        deep=False,
        duplicate_threshold=0.90,
    )


def test_finalize_report_writes_verified_archive(tmp_path: Path) -> None:
    run_dir = tmp_path / "audit-run"
    client = _base_client(run_dir)
    client.records.append(
        EndpointRecord(
            name="repository",
            endpoint="repos/owner/repo",
            status="VERIFIED",
            ok=True,
            count=None,
            duration_ms=1,
            fetched_at="2026-08-06T00:00:00+00:00",
            returncode=0,
            error=None,
            raw_file="raw/repository.json",
        )
    )
    summary = finalize_report(
        client=client,
        config=_config(),
        run_dir=run_dir,
        core_failures=[],
    )
    assert summary["status"] == "VERIFIED"
    assert summary["exit_code"] == 0
    assert (run_dir / "REPORT.md").is_file()
    assert (run_dir / "SUMMARY.json").is_file()
    assert (run_dir / "ARTIFACT_MANIFEST.json").is_file()
    assert (run_dir / "SHA256SUMS").is_file()
    assert Path(summary["zip"]).is_file()
    assert len(summary["zip_sha256"]) == 64
    stored_summary = json.loads((run_dir / "SUMMARY.json").read_text(encoding="utf-8"))
    assert stored_summary["zip"] == summary["zip"]
    assert stored_summary["exit_code"] == 0


def test_non_core_gap_is_not_reported_as_fully_verified(tmp_path: Path) -> None:
    run_dir = tmp_path / "audit-gap"
    client = _base_client(run_dir)
    client.records.append(
        EndpointRecord(
            name="secret_scanning_alerts_open",
            endpoint="repos/owner/repo/secret-scanning/alerts",
            status="BLOCKED",
            ok=False,
            count=None,
            duration_ms=1,
            fetched_at="2026-08-06T00:00:00+00:00",
            returncode=1,
            error="HTTP 403",
            raw_file="raw/secret_scanning_alerts_open.json",
        )
    )
    summary = finalize_report(
        client=client,
        config=_config(),
        run_dir=run_dir,
        core_failures=[],
    )
    assert summary["status"] == "VERIFIED_WITH_GAPS"
    assert summary["exit_code"] == 0
    report = (run_dir / "REPORT.md").read_text(encoding="utf-8")
    assert "| `secret_scanning_alerts_open` | `BLOCKED` | UNKNOWN |" in report


def test_run_command_normalizes_timeout_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def raise_timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(
            cmd=["gh", "api", "repos/owner/repo"],
            timeout=1,
            output=b"partial output",
        )

    monkeypatch.setattr(subprocess, "run", raise_timeout)

    client = GhClient(repo="owner/repo", run_dir=tmp_path / "timeout")
    completed = client.run_command(
        ["gh", "api", "repos/owner/repo"],
        timeout=1,
    )

    assert completed.returncode == 124
    assert completed.stdout == "partial output"
    assert isinstance(completed.stderr, str)
    assert "TIMEOUT" in completed.stderr


def test_get_list_rejects_non_mapping_payload_for_item_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = GhClient(repo="owner/repo", run_dir=tmp_path / "payload")

    completed = subprocess.CompletedProcess(
        args=["gh", "api", "repos/owner/repo/items"],
        returncode=0,
        stdout='["unexpected-list"]',
        stderr="",
    )

    monkeypatch.setattr(
        client,
        "run_command",
        lambda *args, **kwargs: completed,
    )

    result = client.get_list(
        "items",
        "repos/owner/repo/items",
        item_key="items",
    )

    assert result is None
    assert client.records[-1].status == "FAILED"
    assert client.records[-1].error is not None
    assert "Expected object" in client.records[-1].error


def test_actions_selected_configuration_is_not_requested(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = AuditRunner(
        AuditConfig(
            repo="owner/repo",
            output_root=tmp_path,
        )
    )
    get_names: list[str] = []

    def fake_get(
        name: str,
        endpoint: str,
        **kwargs: object,
    ) -> object:
        get_names.append(name)
        if name == "actions_permissions":
            return {
                "enabled": True,
                "allowed_actions": "all",
            }
        return {}

    def fake_get_list(
        name: str,
        endpoint: str,
        **kwargs: object,
    ) -> list[object]:
        return []

    monkeypatch.setattr(runner.client, "get", fake_get)
    monkeypatch.setattr(runner.client, "get_list", fake_get_list)

    runner._collect_actions()

    assert "actions_selected_actions" not in get_names

    record = next(item for item in runner.client.records if item.name == "actions_selected_actions")
    assert record.status == "NOT_APPLICABLE"
    assert record.ok is True
    assert record.returncode == 0

    raw_path = runner.run_dir / "raw" / "actions_selected_actions.json"
    payload = json.loads(raw_path.read_text(encoding="utf-8"))

    assert payload["_audit"]["status"] == "NOT_APPLICABLE"
    assert payload["_audit"]["returncode"] == 0
    assert payload["_audit"]["error"] is None
    assert "allowed_actions='selected'" in payload["data"]["reason"]


def test_actions_selected_configuration_is_requested_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = AuditRunner(
        AuditConfig(
            repo="owner/repo",
            output_root=tmp_path,
        )
    )
    get_names: list[str] = []

    def fake_get(
        name: str,
        endpoint: str,
        **kwargs: object,
    ) -> object:
        get_names.append(name)
        if name == "actions_permissions":
            return {
                "enabled": True,
                "allowed_actions": "selected",
            }
        if name == "actions_selected_actions":
            return {
                "github_owned_allowed": True,
                "verified_allowed": True,
                "patterns_allowed": [],
            }
        return {}

    def fake_get_list(
        name: str,
        endpoint: str,
        **kwargs: object,
    ) -> list[object]:
        return []

    monkeypatch.setattr(runner.client, "get", fake_get)
    monkeypatch.setattr(runner.client, "get_list", fake_get_list)

    runner._collect_actions()

    assert "actions_selected_actions" in get_names
    assert not any(
        item.name == "actions_selected_actions" and item.status == "NOT_APPLICABLE"
        for item in runner.client.records
    )

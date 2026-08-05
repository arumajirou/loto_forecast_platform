from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.darts_campaign.runtime_bootstrap import (
    RuntimeBootstrapProfile,
    canonical_sha256,
    run_runtime_bootstrap,
)
from loto.darts_campaign.runtime_preflight import file_sha256


def profile(**updates: object) -> RuntimeBootstrapProfile:
    payload: dict[str, object] = {
        "bootstrap_id": "notorch-v1",
        "profile_name": "darts-notorch",
        "project_path": "environments/darts-notorch",
        "runtime_profile_path": "configs/darts_campaign/runtime_preflight_notorch.yaml",
        "lockfile_path": "environments/darts-notorch/uv.lock",
        "python_version": "3.13",
        "preflight_output_path": "artifacts/darts-runtime/notorch/preflight.json",
        "bootstrap_report_path": "artifacts/darts-runtime/notorch/bootstrap.json",
        "approval_path": "artifacts/darts-runtime/notorch/CAMPAIGN_APPROVAL.json",
        "timeout_seconds": 30,
    }
    payload.update(updates)
    return RuntimeBootstrapProfile.model_validate(payload)


def prepare_root(root: Path) -> None:
    project = root / "environments/darts-notorch"
    project.mkdir(parents=True)
    (project / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    config = root / "configs/darts_campaign/runtime_preflight_notorch.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("schema_version: 1\n", encoding="utf-8")
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "run_darts_runtime_preflight.py").write_text("# stub\n", encoding="utf-8")


def fixed_clock() -> datetime:
    return datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


class FakeRunner:
    def __init__(
        self,
        root: Path,
        *,
        lock_code: int = 0,
        sync_code: int = 0,
        preflight_status: str = "PASS",
        malformed: bool = False,
        lock_hash_mismatch: bool = False,
    ) -> None:
        self.root = root
        self.lock_code = lock_code
        self.sync_code = sync_code
        self.preflight_status = preflight_status
        self.malformed = malformed
        self.lock_hash_mismatch = lock_hash_mismatch
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        command = tuple(str(item) for item in command)
        self.commands.append(command)
        action = command[1]
        if action == "lock":
            if self.lock_code == 0:
                lockfile = self.root / "environments/darts-notorch/uv.lock"
                lockfile.write_text("version = 1\nrevision = 3\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, self.lock_code, "lock-out", "lock-err")
        if action == "sync":
            return subprocess.CompletedProcess(command, self.sync_code, "sync-out", "sync-err")
        if action != "run":
            raise AssertionError(command)
        output = Path(command[command.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        if self.malformed:
            output.write_text("{bad", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "preflight-out", "")
        lockfile = self.root / "environments/darts-notorch/uv.lock"
        lock_hash = "0" * 64 if self.lock_hash_mismatch else file_sha256(lockfile)
        payload = {
            "schema_version": 1,
            "profile_name": "darts-notorch",
            "overall_status": self.preflight_status,
            "checks": [
                {
                    "check_id": "lockfile",
                    "status": "PASS",
                    "required": True,
                    "expected": "environments/darts-notorch/uv.lock",
                    "observed": {"size_bytes": lockfile.stat().st_size, "sha256": lock_hash},
                    "detail": "ok",
                }
            ],
            "python_executable": "/tmp/python",
            "process_id": 99,
            "platform": "test",
        }
        payload["report_sha256"] = canonical_sha256(payload)
        output.write_text(json.dumps(payload), encoding="utf-8")
        code = {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[self.preflight_status]
        return subprocess.CompletedProcess(command, code, "preflight-out", "preflight-err")


def run(root: Path, runner: FakeRunner, **kwargs: object):
    return run_runtime_bootstrap(
        profile(),
        root,
        runner=runner,
        uv_locator=lambda _: "/usr/bin/uv",
        clock=fixed_clock,
        process_id=123,
        **kwargs,
    )


def test_unsafe_paths_are_rejected() -> None:
    with pytest.raises(ValidationError, match="repository-relative"):
        profile(project_path="../outside")


def test_lockfile_must_belong_to_selected_project() -> None:
    with pytest.raises(ValidationError, match="selected project"):
        profile(lockfile_path="other/uv.lock")


def test_missing_project_blocks_without_commands_and_removes_stale_approval(tmp_path: Path) -> None:
    config = tmp_path / "configs/darts_campaign/runtime_preflight_notorch.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("schema_version: 1\n", encoding="utf-8")
    approval = tmp_path / "artifacts/darts-runtime/notorch/CAMPAIGN_APPROVAL.json"
    approval.parent.mkdir(parents=True)
    approval.write_text("stale", encoding="utf-8")
    runner = FakeRunner(tmp_path)
    report, token = run(tmp_path, runner)
    assert report.overall_status == "BLOCKED"
    assert token is None
    assert runner.commands == []
    assert not approval.exists()


def test_missing_uv_blocks_before_lock(tmp_path: Path) -> None:
    prepare_root(tmp_path)
    runner = FakeRunner(tmp_path)
    report, token = run_runtime_bootstrap(
        profile(),
        tmp_path,
        runner=runner,
        uv_locator=lambda _: None,
        clock=fixed_clock,
        process_id=123,
    )
    assert report.overall_status == "BLOCKED"
    assert token is None
    assert runner.commands == []


def test_lock_failure_stops_sync_and_preflight(tmp_path: Path) -> None:
    prepare_root(tmp_path)
    runner = FakeRunner(tmp_path, lock_code=2)
    report, token = run(tmp_path, runner)
    assert report.overall_status == "BLOCKED"
    assert token is None
    assert [command[1] for command in runner.commands] == ["lock"]


def test_sync_failure_stops_preflight(tmp_path: Path) -> None:
    prepare_root(tmp_path)
    runner = FakeRunner(tmp_path, sync_code=3)
    report, token = run(tmp_path, runner)
    assert report.overall_status == "BLOCKED"
    assert token is None
    assert [command[1] for command in runner.commands] == ["lock", "sync"]


def test_malformed_preflight_report_fails(tmp_path: Path) -> None:
    prepare_root(tmp_path)
    runner = FakeRunner(tmp_path, malformed=True)
    report, token = run(tmp_path, runner)
    assert report.overall_status == "FAIL"
    assert token is None
    assert "invalid preflight report" in report.steps[-1].detail


def test_preflight_lock_hash_mismatch_fails(tmp_path: Path) -> None:
    prepare_root(tmp_path)
    runner = FakeRunner(tmp_path, lock_hash_mismatch=True)
    report, token = run(tmp_path, runner)
    assert report.overall_status == "FAIL"
    assert token is None
    assert "lockfile SHA-256 differs" in report.steps[-1].detail


def test_blocked_preflight_never_creates_approval(tmp_path: Path) -> None:
    prepare_root(tmp_path)
    runner = FakeRunner(tmp_path, preflight_status="BLOCKED")
    report, token = run(tmp_path, runner)
    assert report.overall_status == "BLOCKED"
    assert report.preflight_status == "BLOCKED"
    assert token is None


def test_failed_preflight_never_creates_approval(tmp_path: Path) -> None:
    prepare_root(tmp_path)
    runner = FakeRunner(tmp_path, preflight_status="FAIL")
    report, token = run(tmp_path, runner)
    assert report.overall_status == "FAIL"
    assert report.preflight_status == "FAIL"
    assert token is None


def test_passing_bootstrap_creates_bound_approval_and_exact_command_order(tmp_path: Path) -> None:
    prepare_root(tmp_path)
    runner = FakeRunner(tmp_path)
    report, token = run(tmp_path, runner)
    assert report.overall_status == "PASS"
    assert token is not None
    assert [command[1] for command in runner.commands] == ["lock", "sync", "run"]
    assert "--frozen" in runner.commands[1]
    assert "--frozen" in runner.commands[2]
    assert token.lockfile_sha256 == report.lock_after_sha256
    assert token.preflight_report_sha256 == report.preflight_report_sha256
    assert token.bootstrap_report_sha256 == report.report_sha256
    approval_path = tmp_path / profile().approval_path
    assert approval_path.is_file()


def test_report_and_approval_hashes_are_tamper_sensitive(tmp_path: Path) -> None:
    prepare_root(tmp_path)
    report, token = run(tmp_path, FakeRunner(tmp_path))
    assert token is not None
    report_payload = report.model_dump(mode="json")
    report_hash = report_payload.pop("report_sha256")
    assert report_hash == canonical_sha256(report_payload)
    report_payload["process_id"] = 124
    assert report_hash != canonical_sha256(report_payload)
    token_payload = token.model_dump(mode="json")
    token_hash = token_payload.pop("approval_sha256")
    assert token_hash == canonical_sha256(token_payload)
    token_payload["campaign_execution_allowed"] = False
    assert token_hash != canonical_sha256(token_payload)

# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
TEST_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_ROOT))
sys.path.insert(0, str(TEST_ROOT))

from hierarchicalforecast_target.operator import execute
from hierarchicalforecast_target_fixtures import (
    clean_state,
    fake_success_runner,
)


def test_operator_success(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    output = repo / "artifacts/runtime"
    report, code = execute(
        repo,
        Path("artifacts/runtime"),
        Path("artifacts/operator"),
        expected_git_sha="a" * 40,
        skip_sync=True,
        test_mode=True,
        runner=fake_success_runner(output),
        probe=lambda _: clean_state(),
    )
    assert code == 0
    assert report["status"] == "VERIFIED"
    assert report["git_commit"] == "a" * 40
    assert report["git_postflight"]["clean"] is True
    operator_dir = Path(report["operator_directory"])
    assert (operator_dir / "OPERATOR_REPORT.json").is_file()
    assert (operator_dir / "SHA256SUMS").is_file()


def test_operator_version_mismatch_retains_evidence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def runner(command, cwd, stdout_path, stderr_path):
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("1.5.0\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return {
            "command": list(command),
            "cwd": str(cwd),
            "returncode": 0,
            "started_at": "s",
            "finished_at": "f",
            "duration_seconds": 0.1,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }

    report, code = execute(
        repo,
        Path("runtime"),
        Path("operator"),
        expected_git_sha="a" * 40,
        skip_sync=True,
        test_mode=True,
        runner=runner,
        probe=lambda _: clean_state(),
    )
    assert code == 2
    assert report["status"] == "FAILED_VERSION_MISMATCH"
    assert Path(report["operator_directory"], "OPERATOR_REPORT.json").is_file()


def test_operator_dirty_worktree_fails_preflight(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    report, code = execute(
        repo,
        Path("runtime"),
        Path("operator"),
        expected_git_sha="a" * 40,
        skip_sync=True,
        test_mode=True,
        probe=lambda _: {
            "commit": "a" * 40,
            "branch": "test",
            "clean": False,
            "status_porcelain": ["?? dirty.txt"],
        },
    )
    assert code == 3
    assert report["status"] == "FAILED_PREFLIGHT"
    assert "clean worktree" in report["error"]


def test_operator_rejects_postflight_git_drift(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    output = repo / "runtime"
    states = iter(
        [
            clean_state(),
            {
                "commit": "b" * 40,
                "branch": "test",
                "clean": False,
                "status_porcelain": [" M src/file.py"],
            },
        ]
    )
    report, code = execute(
        repo,
        Path("runtime"),
        Path("operator"),
        expected_git_sha="a" * 40,
        skip_sync=True,
        test_mode=True,
        runner=fake_success_runner(output),
        probe=lambda _: next(states),
    )
    assert code == 3
    assert report["status"] == "FAILED_POSTFLIGHT_GIT_DRIFT"
    assert report["formal_success"] is False


def test_skip_sync_is_rejected_outside_test_mode(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    report, code = execute(
        repo,
        Path("runtime"),
        Path("operator"),
        expected_git_sha="a" * 40,
        skip_sync=True,
        probe=lambda _: clean_state(),
    )
    assert code == 3
    assert report["status"] == "FAILED_PREFLIGHT"
    assert "only be skipped" in report["error"]


def test_expected_git_sha_is_required_outside_test_mode(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    report, code = execute(
        repo,
        Path("runtime"),
        Path("operator"),
        probe=lambda _: clean_state(),
    )
    assert code == 3
    assert report["status"] == "FAILED_PREFLIGHT"
    assert "expected-git-sha" in report["error"]

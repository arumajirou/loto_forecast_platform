from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from loto.merlion_campaign.git_provenance import (
    build_git_provenance,
    parse_git_porcelain_z,
    validate_git_provenance,
)


def _runner_factory(*, dirty: bool, branch: str = "feature") -> object:
    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del kwargs
        args = command[3:]
        if args == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, b"a" * 40 + b"\n", b"")
        if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, branch.encode() + b"\n", b"")
        if args == ["status", "--porcelain=v1", "-z", "--untracked-files=all"]:
            data = b" M pyproject.toml\x00" if dirty else b""
            return subprocess.CompletedProcess(command, 0, data, b"")
        raise AssertionError(command)

    return runner


def test_clean_git_provenance_is_hash_bound(tmp_path: Path) -> None:
    report = build_git_provenance(tmp_path, runner=_runner_factory(dirty=False))
    assert report["status"] == "CLEAN"
    validate_git_provenance(report, require_clean=True)


def test_dirty_git_provenance_is_blocked(tmp_path: Path) -> None:
    report = build_git_provenance(tmp_path, runner=_runner_factory(dirty=True))
    assert report["status"] == "BLOCKED"
    assert "GIT_WORKTREE_NOT_CLEAN" in report["blockers"]
    with pytest.raises(ValueError, match="not CLEAN"):
        validate_git_provenance(report, require_clean=True)


def test_detached_head_is_blocked(tmp_path: Path) -> None:
    report = build_git_provenance(
        tmp_path,
        runner=_runner_factory(dirty=False, branch="HEAD"),
    )
    assert "GIT_DETACHED_HEAD" in report["blockers"]


def test_porcelain_parser_records_rename_source() -> None:
    assert parse_git_porcelain_z(b"R  new.py\x00old.py\x00") == [
        {"status": "R ", "path": "new.py", "source_path": "old.py"}
    ]

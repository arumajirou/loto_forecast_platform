from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from loto.moirai2_campaign.runtime_source_identity import (
    RuntimeSourceIdentityError,
    capture_source_identity,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    source = root / "source.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "add", "source.py")
    _git(root, "commit", "-m", "initial")
    return root


def test_clean_repository_identity_is_retained(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    evidence = capture_source_identity(
        repo_root=root,
        principal_paths=("source.py",),
    )
    assert len(evidence["commit_sha"]) == 40
    assert len(evidence["tree_sha"]) == 40
    assert evidence["worktree_clean"] is True
    assert len(evidence["principal_file_sha256"]["source.py"]) == 64


def test_dirty_repository_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "source.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(RuntimeSourceIdentityError, match="clean worktree"):
        capture_source_identity(
            repo_root=root,
            principal_paths=("source.py",),
        )


def test_untracked_file_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "untracked.txt").write_text("x\n", encoding="utf-8")
    with pytest.raises(RuntimeSourceIdentityError, match="untracked.txt"):
        capture_source_identity(
            repo_root=root,
            principal_paths=("source.py",),
        )


def test_missing_principal_source_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    with pytest.raises(RuntimeSourceIdentityError, match="missing.py"):
        capture_source_identity(
            repo_root=root,
            principal_paths=("missing.py",),
        )

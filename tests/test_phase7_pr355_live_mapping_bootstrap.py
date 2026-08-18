from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO / "tools" / "phase7_holdout_runner" / "pr355_live_mapping_bootstrap.py"
)
SPEC = importlib.util.spec_from_file_location("phase7_pr355_bootstrap", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_fetch_pr_head_uses_fetch_head_without_switching(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run_git(repo: Path, *args: str, capture: bool = True):
        calls.append(args)
        if args[:2] == ("fetch", "origin"):
            return subprocess.CompletedProcess([], 0, "", "")
        if args == ("rev-parse", "FETCH_HEAD"):
            return subprocess.CompletedProcess([], 0, "a" * 40 + "\n", "")
        raise AssertionError(args)

    monkeypatch.setattr(MOD, "run_git", fake_run_git)

    assert MOD.fetch_pr_head(Path("repo")) == "a" * 40
    assert calls == [
        ("fetch", "origin", MOD.PR_BRANCH),
        ("rev-parse", "FETCH_HEAD"),
    ]


def test_worktree_operations_are_detached_and_scoped(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run_git(repo: Path, *args: str, capture: bool = True):
        calls.append(args)
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(MOD, "run_git", fake_run_git)

    repo = tmp_path / "repo"
    worktree = tmp_path / "isolated"

    MOD.add_detached_worktree(repo, worktree, "b" * 40)
    MOD.remove_worktree(repo, worktree)

    assert calls == [
        ("worktree", "add", "--detach", str(worktree), "b" * 40),
        ("worktree", "remove", str(worktree)),
    ]

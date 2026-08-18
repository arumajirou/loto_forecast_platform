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


def test_materialize_pr_files_uses_only_git_show(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []

    def fake_git_show_bytes(repo: Path, head: str, path: str) -> bytes:
        calls.append((head, path))
        return ("payload:" + path).encode("utf-8")

    monkeypatch.setattr(MOD, "git_show_bytes", fake_git_show_bytes)

    repo = tmp_path / "repo"
    root = tmp_path / "isolated"
    head = "b" * 40

    MOD.materialize_pr_files(repo, root, head)

    assert calls == [(head, path) for path in MOD.MATERIALIZED_PATHS]
    for relative in MOD.MATERIALIZED_PATHS:
        destination = root / relative
        assert destination.read_bytes() == ("payload:" + relative).encode("utf-8")


def test_materialization_does_not_use_git_worktree(monkeypatch, tmp_path: Path) -> None:
    def forbidden_run_git(*args, **kwargs):
        raise AssertionError("git worktree must not be used for selective materialization")

    monkeypatch.setattr(MOD, "run_git", forbidden_run_git)
    monkeypatch.setattr(
        MOD,
        "git_show_bytes",
        lambda repo, head, path: b"x",
    )

    root = tmp_path / "isolated"
    MOD.materialize_pr_files(tmp_path / "repo", root, "c" * 40)

    assert root.is_dir()


def test_remove_materialized_root_is_scoped(tmp_path: Path) -> None:
    root = tmp_path / "isolated"
    root.mkdir()
    (root / "file.txt").write_text("x", encoding="utf-8")

    MOD.remove_materialized_root(root)

    assert not root.exists()
